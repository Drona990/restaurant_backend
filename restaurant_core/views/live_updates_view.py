import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from restaurant_core.utils import broadcast_order_update
from restaurant_core.models import GuestSession, MenuItem, Order, OrderItem, Table
from restaurant_core.serializers import KDSOrderSerializer, TableFloorMapSerializer
from django.db.models import Sum


class SubmitOrderView(APIView):
    """
    Handles New Orders and Add-ons.
    Waiter -> Auto-confirms & notifies KDS.
    Customer -> Sets pending & notifies Waiter.
    Updates GuestSession on first order.
    """
    @transaction.atomic
    def post(self, request):
        try:
            data = request.data
            table_id = data.get('table_id')
            session_id = data.get('session_id') # From Angular
            order_id = data.get('order_id')     # From Angular for Add-ons
            items_data = data.get('items', [])
            group_tag = data.get('group_tag', 'Group A')
            
            # Robust Boolean Check (from your Version 1)
            is_waiter = str(data.get('is_waiter', 'false')).lower() == 'true'

            if not items_data:
                return Response({"error": "No items provided"}, status=400)

            table = get_object_or_404(Table, id=table_id)

            # --- A. Create or Get Order ---
            if order_id:
                # Add-on Scenario: Purana unpaid order fetch karo
                order = get_object_or_404(Order, id=order_id, is_paid=False)
            else:
                # First Order Scenario: Naya order banao
                customer_name = data.get('customer_name') or items_data[0].get('guest', 'Guest')
                order = Order.objects.create(
                    table=table,
                    group_tag=group_tag,
                    is_paid=False,
                    waiter=request.user if is_waiter else None,
                    customer_name=customer_name,
                    status='preparing'
                )
                
                # 🌟 Link GuestSession with Order (Crucial for Rescan logic)
                if session_id:
                    GuestSession.objects.filter(id=session_id).update(
                        order_id=order.id, 
                        is_active=True
                    )

                table.is_occupied = True
                if is_waiter and not table.assigned_waiter:
                    table.assigned_waiter = request.user
                table.save()

            # --- B. Add Order Items & Set Status ---
            stations_to_notify = set()
            new_items_summary = []

            for item in items_data:
                m_id = item.get('menu_item_id') or item.get('id')
                menu_item = get_object_or_404(MenuItem, id=m_id)
                
                # 🌟 AUTO-APPROVE LOGIC (From your Version 1)
                item_status = 'confirmed' if is_waiter else 'pending'
                
                oi = OrderItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=item.get('qty') or item.get('quantity', 1),
                    unit_price=menu_item.price,
                    ordered_by_name=item.get('guest', order.customer_name),
                    status=item_status
                )

                if item_status == 'confirmed':
                    stations_to_notify.add(menu_item.category.station.lower())
                
                new_items_summary.append({
                    "name": menu_item.name,
                    "status": item_status,
                    "qty": oi.quantity
                })

            # --- C. Real-time Notifications (From your Version 1) ---
            if not is_waiter:
                # Customer ne order kiya -> Waiter ko approve karne ke liye bolo
                broadcast_order_update(
                    'waiter_only', 
                    table.table_number, 
                    "NEW_TICKET", 
                    f"Table {table.table_number} needs approval"
                )
            else:
                # Waiter ne order kiya -> Seedha Kitchen (KDS) ko bhejo
                for st in stations_to_notify:
                    broadcast_order_update(
                        st, 
                        table.table_number, 
                        "NEW_TICKET", 
                        f"New Order: Table {table.table_number}"
                    )

           
            broadcast_order_update(
                 f"table_{table.id}",       # 1. target (room)
                 "NEW_ITEM_ADDED",          # 2. notify_type (Missing tha)
                 "Items added to cart",     # 3. message (Missing tha)
                 {"items": new_items_summary} # 4. data/payloa
)

            return Response({
                "status": "Success", 
                "order_id": order.id,
                "invoice": getattr(order, 'invoice_number', 'N/A')
            }, status=201)

        except Exception as e:
            print("❌ SUBMIT ORDER CRASHED:")
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=500)



class OrderTrackingView(APIView):
    def get(self, request):
        try:
            session_id = request.query_params.get('session_id')
            if not session_id:
                return Response({"error": "Session ID is required"}, status=400)

            # 1. Check if Session exists
            guest_session = get_object_or_404(GuestSession, id=session_id)
            
            # 2. Check if Order is linked
            if not guest_session.order_id:
                return Response({"items": [], "message": "No active order for this session"}, status=200)

            # 3. Fetch Items Safely
            # order_id se direct filter karna safe hai
            items = OrderItem.objects.filter(order_id=guest_session.order_id).select_related('menu_item', 'order')
            
            history = []
            is_paid = False
            
            for it in items:
                # Pehle item se order ka payment status utha lo
                is_paid = it.order.is_paid 
                
                history.append({
                    "id": it.menu_item.id,
                    "menu_item_id": it.menu_item.id,
                    "name": it.menu_item.name,
                    "status": it.status,
                    "quantity": it.quantity,
                    "unit_price": float(it.unit_price), # 👈 Price bhejna zaruri hai
                    "order_id": it.order_id,
                    "updated_at": it.created_at.isoformat() if it.created_at else None
                })
                

            return Response({
                "items": history,
                "is_paid": is_paid,
                "order_id": guest_session.order_id
            }, status=200)

        except Exception as e:
            print("❌ HISTORY FETCH ERROR:")
            print(traceback.format_exc()) # 👈 Terminal check karein
            return Response({"error": str(e)}, status=500)


class InitializeSessionView(APIView):
    """
    Checks if a session is still valid or settled.
    """
    def post(self, request):
        sid = request.data.get('session_id')
        table_no = request.data.get('table_no')
        
        # Get or create session
        session, created = GuestSession.objects.get_or_create(
            id=sid, 
            defaults={'table_number': table_no, 'is_active': True}
        )

        # 🌟 Logic: Agar bill paid ho gaya hai, toh session inactive hai
        is_settled = False
        if session.order_id:
            order = Order.objects.filter(id=session.order_id).first()
            if order and order.is_paid:
                is_settled = True
                session.is_active = False
                session.save()

        return Response({
            "session_id": sid,
            "order_id": session.order_id if not is_settled else None,
            "is_active": session.is_active and not is_settled,
            "is_settled": is_settled
        })

# --- 2. KDS VIEWS (Chef & Barman) ---
class StationKDSView(APIView):
    """
    Fetch pending items specifically for the logged-in staff's station.
    """
    def get(self, request):
        user_role = request.user.role.lower()
        target_station = 'bar' if user_role == 'barman' else 'kitchen'

        orders = Order.objects.filter(
            items__menu_item__category__station=target_station,
            items__status__in=['confirmed', 'cooking'],
            is_paid=False
        ).distinct()

        serializer = KDSOrderSerializer(orders, many=True)
        return Response({"data": serializer.data})



class UpdateItemStatusView(APIView):
    """
    Handles Status Updates:
    - Waiter: 'confirmed' (Accept) or 'served' (Serve)
    - Chef: 'cooking' (Start) or 'ready' (Finish)
    """
    @transaction.atomic
    def patch(self, request):
        item_ids = request.data.get('item_ids', [])
        new_status = request.data.get('status') # confirmed, cooking, ready, served
        user = request.user

        items = OrderItem.objects.filter(id__in=item_ids)
        if not items.exists():
            return Response({"error": "No items found"}, status=404)

        first_item = items.first()
        table_no = first_item.order.table.table_number
        station = first_item.menu_item.category.station.lower()

        # 1. Update items in DB
        for item in items:
            if new_status == 'cooking':
                item.assigned_chef = user
            item.status = new_status
            item.save()

        # 2. Logic: Kise notify karna hai?
        
        # Case A: Waiter ne ACCEPT kiya (Confirmed) -> Notify CHEF
        if new_status == 'confirmed':
            broadcast_order_update(station, table_no, "NEW_TICKET", f"T-{table_no}: New Order Accepted")
            
        # Case B: Chef ne START kiya (Cooking) -> Silent refresh for other CHEFS
        elif new_status == 'cooking':
            broadcast_order_update(station, table_no, "KDS_REFRESH", "Chef started cooking")
            
        # Case C: Chef ne READY kiya (Ready) -> Notify WAITER (Alert/Sound)
        elif new_status == 'ready':
            # 'waiter_only' targets the Waiter app specifically
            broadcast_order_update("waiter_only", table_no, "STATUS_UPDATE", f"T-{table_no}: Food is Ready!", {"status": "ready"})
            
        # Case D: Waiter ne SERVE kiya (Served) -> Silent refresh for Everyone
            # Case D: Waiter ne SERVE kiya (Served)
        elif new_status == 'served':
            # 1. Staff aur Admin Refresh (both = kitchen + bar + waiters)
            broadcast_order_update(
                station="both", 
                table_no=table_no, 
                notify_type="STATUS_UPDATE", 
                message=f"Table {table_no} items served",
                data={"order_id": first_item.order.id}
            )
            
            # 2. Customer Screen Refresh (Specific Table Room)
            # Yahan table.id use karein kyunki Angular room ID se join karta hai
            table_id = first_item.order.table.id
            broadcast_order_update(
                station=f"table_{table_id}", 
                table_no=table_no, 
                notify_type="STATUS_UPDATE", 
                message="Your food is served. Enjoy!",
                data={"status": "served"}
            )
            print(f"📢 Broadcast sent to both Staff and Customer (Table {table_no})")
            broadcast_order_update("all_staff", table_no, "KDS_REFRESH", "Item served")

        return Response({"success": True, "new_status": new_status})


# --- 3. WAITER ACTIONS (Approve & Serve) ---
class WaiterActionView(APIView):
    """
    Approving Pending orders or marking Ready items as Served.
    """
    def post(self, request):
        item_id = request.data.get('item_id')
        action = request.data.get('action') # 'approve' or 'serve'
        item = get_object_or_404(OrderItem, id=item_id)
        station = item.menu_item.category.station.lower()

        if action == 'approve':
            item.status = 'confirmed'
            item.save()
            broadcast_order_update(station, item.order.table.table_number, "NEW_TICKET", f"{item.menu_item.name} Approved!")
            return Response({"message": "Approved"})

        elif action == 'serve':
            item.status = 'served'
            item.save()
            broadcast_order_update('waiter_only', item.order.table.table_number, "ITEM_SERVED", "Served")
            return Response({"message": "Served"})

        return Response({"error": "Invalid Action"}, status=400)


# --- 4. ADMIN & ANALYTICS VIEWS ---

class AdminLiveDashboardView1(APIView):
    """
    Manager's God-Eye View: 
    Returns: 
    1. Stats (Revenue, Active KOTs)
    2. Floor Map (Tables with Nested Live Orders & Items)
    """
    def get(self, request):
        try:
            # 1. Floor Map with Nested Orders (Using your serializer)
            tables = Table.objects.all().order_by('table_number')
            floor_data = TableFloorMapSerializer(tables, many=True).data

            # 2. Live Analytics for Ribbons
            active_orders = Order.objects.filter(is_paid=False)
            stats = {
                "total_revenue": active_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
                "active_sessions": active_orders.count(),
                "pending_kot": OrderItem.objects.filter(status='confirmed').count(),
                "ready_to_serve": OrderItem.objects.filter(status='ready').count(),
            }

            return Response({
                "success": True,
                "stats": stats,
                "tables": floor_data,
            }, status=200)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)    


class AdminLiveDashboardView(APIView):
    def get(self, request):
        try:
            tables = Table.objects.all().order_by('table_number')
            # Data fetch karte waqt error yahan ho sakta hai
            floor_data = TableFloorMapSerializer(tables, many=True).data

            active_orders = Order.objects.filter(is_paid=False)
            stats = {
                "total_revenue": active_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
                "occupied_tables": tables.filter(is_occupied=True).count(),
                "pending_kot": OrderItem.objects.filter(status='confirmed').count(),
                "ready_items": OrderItem.objects.filter(status='ready').count(),
            }

            return Response({
                "success": True,
                "stats": stats,
                "tables": floor_data,
            }, status=200)

        except Exception as e:
            # 🌟 YEH HAI LOGGING: Terminal mein exact error dikhega
            print("❌ ADMIN DASHBOARD ERROR:", str(e))
            traceback.print_exc() 
            return Response({
                "success": False, 
                "error": str(e),
                "traceback": traceback.format_exc() # Development ke liye isse bhej sakte hain
            }, status=500)


class CompleteTicketView(APIView):
    """
    Chef/Barman ek sath poore ticket (apne station ke items) ko 'Ready' mark karta hai.
    """
    @transaction.atomic
    def post(self, request):
        try:
            order_id = request.data.get('order_id')
            user_role = request.user.role.lower()
            
            # 🎯 1. Station identify karein (User role se)
            station = 'bar' if user_role == 'barman' else 'kitchen'

            # 🎯 2. Is order ke saare items uthao jo is station ke hain aur abhi ready nahi hue
            items_to_update = OrderItem.objects.filter(
                order_id=order_id, 
                menu_item__category__station=station
            ).exclude(status__in=['ready', 'served', 'cancelled'])

            if not items_to_update.exists():
                return Response({"error": "No pending items for your station in this ticket"}, status=400)

            # 🎯 3. Status update
            items_to_update.update(status='ready')
            
            # 🎯 4. Master Broadcast (Waiter aur Customer ko notify karo)
            order = get_object_or_404(Order, id=order_id)
            broadcast_order_update(
                station=f"{station}_ready", 
                table_no=order.table.table_number, 
                notify_type="STATUS_UPDATE", 
                message=f"T-{order.table.table_number}: All {station} items are READY!"
            )

            return Response({"status": "Success", "message": f"All {station} items marked as ready"})

        except Exception as e:
            return Response({"error": str(e)}, status=500)