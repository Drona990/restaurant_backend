from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from restaurant_core.models import GuestSession, Order, Table
from restaurant_core.serializers import WaiterTableSerializer
import traceback

class ClaimTableView(APIView):
    permission_classes = [IsAuthenticated] 

    def post(self, request, identifier):
        print(f"DEBUG: Claiming Identifier -> {identifier}") # 👈 Check terminal
        user = request.user
        try:
            # 1. 🤝 JOIN GROUP LOGIC: Agar scan 'INV-' hai
            if str(identifier).startswith('INV-'):
                active_order = get_object_or_404(Order, invoice_number=identifier, is_paid=False)
                
                table = active_order.table
                table.assigned_waiter = user
                table.save()

                return Response({
                    "message": f"Joined {active_order.customer_name}'s group",
                    "order_id": active_order.id,
                    "mode": "JOINED"
                }, status=200)

            # 2. 🆕 NEW SESSION: Agar identifier Table ID (Number) hai
            # Yahan hum check kar rahe hain ki identifier valid integer hai ya nahi
            table = get_object_or_404(Table, id=identifier)
            
            table.assigned_waiter = user
            table.is_occupied = True
            table.save()

            return Response({
                "message": "Table claimed. Start a new session.",
                "table_id": table.id,
                "mode": "NEW_SESSION"
            }, status=200)

        except Exception as e:
            # 🚨 Terminal pe error check karne ke liye
            print(f"--- CLAIM TABLE ERROR ---")
            print(f"Identifier: {identifier}")
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)
 

class MyTablesView(APIView):
    """
    Waiter Dashboard: Wahi tables dikhao jo is waiter ki hain ya jinpar active orders hain.
    """
    def get(self, request):
        try:
            # 1. 🛡️ User Check
            if not request.user.is_authenticated:
                return Response({"error": "Unauthorized"}, status=401)

            # 2. Query Logic: Filter tables assigned to this waiter OR having active orders by this waiter
            tables = Table.objects.filter(
                Q(assigned_waiter=request.user) | 
                Q(orders__waiter=request.user, orders__is_paid=False)
            ).distinct().order_by('table_number')

            # 3. Serialization
            serializer = WaiterTableSerializer(tables, many=True)
            
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # ❗ Terminal mein error print karega exact wajah janne ke liye
            import traceback
            print("🔥 MyTablesView CRASHED:")
            print(traceback.format_exc())
            
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
