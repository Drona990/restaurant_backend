from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
from restaurant_core.models import Order
from django.utils.timezone import now, make_aware
import datetime
from django.db.models import Sum, DecimalField, Q, Count
from django.utils.timezone import now
from datetime import timedelta
from core.permissions import IsStaffOrHigher

class AnalyticsView(APIView):
    def get(self, request):
        try:
            range_type = request.query_params.get('range', 'today')
            
            # 🌟 Timezone Aware Date Range Logic
            # now() use karna safe hai
            current_now = now()
            today_start = current_now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            if range_type == 'today':
                start_date = today_start
            else:
                # Month-to-date logic
                start_date = today_start.replace(day=1)

            # 🌟 Filter: Paid orders within the range
            orders = Order.objects.filter(is_paid=True, updated_at__gte=start_date)
            
            # Aggregation logic
            stats = orders.aggregate(
                gross_revenue=Coalesce(Sum('total_amount'), Decimal('0.00'), output_field=DecimalField()),
                total_discount=Coalesce(Sum('discount_amount'), Decimal('0.00'), output_field=DecimalField())
            )

            gross = stats['gross_revenue']
            discount = stats['total_discount']
            
            net_revenue = float(gross - discount)
            
            estimated_gst = (net_revenue * 18) / 118 

            return Response({
                "data": {
                    "total_revenue": round(net_revenue, 2),
                    "total_gst": round(estimated_gst, 2),
                    "total_invoices": orders.count(),
                    "total_discount_given": float(discount)
                }
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({
                "data": {
                    "total_revenue": 0,
                    "total_gst": 0,
                    "total_invoices": 0,
                }
            }, status=200)




class AdvancedAnalyticsView(APIView):
    permission_classes = [IsStaffOrHigher]
    def get(self, request):
        try:
            range_type = request.query_params.get('range', 'today') # today, weekly, monthly, custom
            start_str = request.query_params.get('start_date') # Format: YYYY-MM-DD
            end_str = request.query_params.get('end_date')

            current_now = now()
            today_start = current_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = current_now # Default end is now

            # 📅 Advanced Date Logic
            if range_type == 'today':
                start_date = today_start
            elif range_type == 'weekly':
                start_date = today_start - timedelta(days=7)
            elif range_type == 'monthly':
                start_date = today_start.replace(day=1)
            elif range_type == 'custom' and start_str and end_str:
                from django.utils.dateparse import parse_date
                start_date = make_aware(datetime.datetime.combine(parse_date(start_str), datetime.time.min))
                end_date = make_aware(datetime.datetime.combine(parse_date(end_str), datetime.time.max))
            else:
                start_date = today_start

            # 🌟 Powerful Aggregation: Cash vs UPI vs Card
            orders = Order.objects.filter(is_paid=True, paid_at__range=(start_date, end_date))
            
            stats = orders.aggregate(
                gross_revenue=Coalesce(Sum('total_amount'), Decimal('0.00'), output_field=DecimalField()),
                total_discount=Coalesce(Sum('discount_amount'), Decimal('0.00'), output_field=DecimalField()),
                # Conditional Sums for Payment Methods
                cash_sales=Coalesce(Sum('total_amount', filter=Q(payment_method__iexact='Cash')), Decimal('0.00'), output_field=DecimalField()),
                upi_sales=Coalesce(Sum('total_amount', filter=Q(payment_method__iexact='Upi')), Decimal('0.00'), output_field=DecimalField()),
                card_sales=Coalesce(Sum('total_amount', filter=Q(payment_method__iexact='Card')), Decimal('0.00'), output_field=DecimalField()),
                # Order counts
                completed_count=Count('id'),
            )

            # Calculations
            net_revenue = stats['gross_revenue'] # Hamare logic mein total_amount pehle se discount-deducted hai
            # Agar aapka total_amount gross hai, toh: net = stats['gross_revenue'] - stats['total_discount']
            
            # Tax Calculation (Assuming 5% GST for Restaurant)
            gst_amount = (net_revenue * Decimal('0.05')) / Decimal('1.05')

            return Response({
                "status": "success",
                "range": range_type,
                "data": {
                    "summary": {
                        "net_revenue": round(float(net_revenue), 2),
                        "gst_collected": round(float(gst_amount), 2),
                        "total_orders": stats['completed_count'],
                        "total_discount": round(float(stats['total_discount']), 2),
                    },
                    "payment_breakdown": {
                        "cash": round(float(stats['cash_sales']), 2),
                        "upi": round(float(stats['upi_sales']), 2),
                        "card": round(float(stats['card_sales']), 2),
                    }
                }
            })

        except Exception as e:
            return Response({"error": str(e)}, status=400)