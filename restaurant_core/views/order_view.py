import logging
from django.utils import timezone  
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now, localdate
from datetime import timedelta
from rest_framework.response import Response
from core.permissions import IsStaffOrHigher
from restaurant_core.models import Discount, GuestSession, Table, MenuItem, Order, OrderItem
from restaurant_core.serializers import OrderCreateSerializer, OrderItemSerializer, OrderListSerializer
from restaurant_core.utils import APIResponse, broadcast_order_update
from rest_framework import status
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from decimal import ROUND_HALF_UP, Decimal


logger = logging.getLogger(__name__)

class PlaceOrderView(APIView):
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        # 1. Frontend se aaya hua raw data check karein
        print("--- FRONTEND SE AAYA DATA (RAW) ---")
        print(request.data) 
        
        serializer = OrderCreateSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                order = serializer.save()
                
                response_data = OrderListSerializer(order).data
                
                print("--- BACKEND SE BHEJA JA RAHA DATA (SUCCESS) ---")
                print(response_data)
                
                return Response({
                    "success": True,
                    "message": "Order placed!",
                    "data": response_data
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                print(f"ERROR OCCURRED: {str(e)}")
                return Response({"success": False, "message": str(e)}, status=500)
        
        # 3. Agar validation fail ho jaye
        print("--- VALIDATION ERRORS ---")
        print(serializer.errors)
        return Response({"success": False, "errors": serializer.errors}, status=400)


class OrderListView(APIView):
    permission_classes = [IsAuthenticated] 

    def get(self, request):
        try:
            user = request.user
            today = timezone.now().date()
            
            # 1. Base Query
            queryset = Order.objects.filter(created_at__date=today)

            # 2. Role Filtering
            role = getattr(user, 'role', '').lower()
            if role == 'chef':
                queryset = queryset.filter(items__menu_item__category__station='kitchen')
            elif role == 'barman':
                queryset = queryset.filter(items__menu_item__category__station='bar')

            # 3. Serialize Data
            orders = queryset.distinct().order_by('-created_at')
            serializer = OrderListSerializer(orders, many=True)
            
            return Response({
                "success": True,
                "data": serializer.data
            })

        except Exception as e:
            # 🚨 Ye line terminal mein asli error dikhayegi
            print(f"--- ORDER LIST CRASH: {str(e)} ---")
            logger.error(f"Order List Error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": f"Server Error: {str(e)}"
            }, status=500)

class OrderHistoryView(APIView):
    permission_classes = [IsStaffOrHigher]

    def get(self, request):
        range_type = request.query_params.get('range', 'today')
        payment_mode = request.query_params.get('payment_mode', 'all')
        search = request.query_params.get('search', '')

        # Filter check: 🌟 is_paid=True sirf purani history ke liye hai. 
        # Agar live orders chahiye toh is_paid=False karein.
        queryset = Order.objects.filter(is_paid=True).select_related('table').prefetch_related('items__menu_item').order_by('-created_at')

        today = localdate()
        if range_type == 'today':
            queryset = queryset.filter(created_at__date=today)
        elif range_type == 'yesterday':
            queryset = queryset.filter(created_at__date=today - timedelta(days=1))

        if payment_mode != 'all':
            queryset = queryset.filter(payment_method__iexact=payment_mode)
            
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search) | 
                Q(customer_name__icontains=search)
            )

        data = []
        for o in queryset:
            data.append({
                "id": o.id,
                "invoice": o.invoice_number,
                "datetime": o.created_at.strftime('%d %b, %I:%M %p'),
                "table": o.table.table_number if o.table else "N/A",
                "customer": o.customer_name,
                "amount": float(o.total_amount),
                "payment": o.payment_method.upper() if o.payment_method else "CASH",
                "items": [
                    {
                        "name": item.menu_item.name,
                        "qty": item.quantity,
                        "status": item.status
                    } for item in o.items.all()
                ]
            })

        # 🌟 Flutter compatibility: 'data' key ke andar response bhejien
        return Response({"success": True, "data": data})


# --- 2. KDS VIEW (Chef Updates Status) ---

class KDSUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_station = request.query_params.get('station')
        queryset = OrderItem.objects.filter(
            status__in=['confirmed', 'cooking']
        ).select_related('menu_item__category', 'order__table').order_by('created_at')

        if target_station:
            queryset = queryset.filter(menu_item__category__station__iexact=target_station)

        serializer = OrderItemSerializer(queryset, many=True)
        return Response(serializer.data)

    def patch(self, request):
        item_id = request.data.get('item_id')
        new_status = request.data.get('status')
        item = get_object_or_404(OrderItem, id=item_id)
        
        if new_status in ['cooking', 'ready', 'served']:
            item.status = new_status
            if new_status == 'cooking':
                item.assigned_chef = request.user 
            item.save()

            # 🌟 WebSocket: Notify Waiter
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "waiters_group", 
                {
                    "type": "order_notification", 
                    "notification_type": "item_ready" if new_status == 'ready' else "order_update",
                    "message": f"Table {item.order.table.table_number}: {item.menu_item.name} is {new_status}"
                }
            )
            return Response({"success": True, "message": f"Updated to {new_status}"})
        return Response({"error": "Invalid status"}, status=400)

# --- 3. BILLING VIEW (Auto Discount + Thermal Receipt) ---


class GenerateBillView(APIView):
    permission_classes = [IsStaffOrHigher]

    def post(self, request):
        print("\n🚀 --- STARTING BILL GENERATION ---")
        order_id = request.data.get('order_id')
        payment_method = request.data.get('payment_method', 'Cash').capitalize()
        user_coupon = request.data.get('coupon_code', None)

        try:
            with transaction.atomic():
                # 1. Order aur Items fetch karein
                order = Order.objects.select_for_update().get(id=order_id, is_paid=False)
                items = order.items.all()
                
                # 2. Calculation Logic
                subtotal = sum(Decimal(str(it.quantity)) * it.unit_price for it in items)
                subtotal = subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # 3. Discount Engine
                now = timezone.now()
                best_discount_amt = Decimal('0.00')
                applied_offer_name = "No Offer"
                discounts = Discount.objects.filter(is_active=True, min_purchase__lte=subtotal).filter(
                    Q(discount_type='THRESHOLD') |
                    Q(discount_type='FESTIVAL', valid_from__lte=now, valid_to__gte=now) |
                    Q(discount_type='COUPON', code=user_coupon)
                )
                for d in discounts:
                    amt = subtotal * (d.value / Decimal('100')) if d.value_type == 'PERCENT' else d.value
                    if amt > best_discount_amt:
                        best_discount_amt = amt
                        applied_offer_name = d.name

                # 4. Save Logic
                order.is_paid = True
                order.payment_method = payment_method
                order.total_amount = (subtotal - best_discount_amt) * Decimal('1.18') # 18% tax example
                order.status = 'completed'
                order.paid_at = timezone.now()
                order.save()

                if order.table:
                    order.table.is_occupied = False
                    order.table.save()

                # 5. Bill Parcha Structure (For PDF Printing)
                bill_parcha = {
                    "header": {"name": "SVENSKA RESTAURANT", "address": "Bengaluru, Karnataka"},
                    "meta": {
                        "inv": f"{order.invoice_number}",
                        "order_id": f"{order.id}", 
                        "table": order.table.table_number if order.table else "N/A",
                        "waiter": order.waiter.username if order.waiter else "Staff",
                        "method": payment_method,
                        "time": order.paid_at.strftime("%d-%b-%Y %I:%M %p") 
                    },
                    "items": [
                        {"name": it.menu_item.name, "qty": int(it.quantity), "total": str((it.quantity * it.unit_price).quantize(Decimal('0.01')))} 
                        for it in items
                    ],
                    "summary": {
                        "subtotal": str(subtotal),
                        "offer": applied_offer_name,
                        "discount": str(best_discount_amt),
                        "grand_total": str(order.total_amount.quantize(Decimal('0.01')))
                    }
                }

                # --- 📡 THE MAGIC PART (On Commit) ---
                # Ye tabhi chalega jab response success ho jayega
                def send_signals():
                    print("📡 Printing signal sending now...")
                    # Waiter Refresh
                    broadcast_order_update(
                        station='both', 
                        table_no=order.table.table_number if order.table else 0,
                        notify_type='PAYMENT_CONFIRMED',
                        message=f"Bill Settled",
                        data={"order_id": order.id}
                    )
                    # Customer Refresh
                    if order.table:
                        broadcast_order_update(
                            station=f"table_{order.table.id}", 
                            table_no=order.table.table_number,
                            notify_type='STATUS_UPDATE',
                            message="Thank You!",
                            data={"is_paid": True}
                        )

                transaction.on_commit(send_signals)

            print("✅ Bill data sent to App. Printing should start.")
            return Response({"success": True, "data": bill_parcha})

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            return Response({"error": str(e)}, status=500)