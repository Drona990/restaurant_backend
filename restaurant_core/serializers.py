from rest_framework import serializers
from decimal import Decimal
from django.db import transaction
from .models import Discount, Table, Category, MenuItem, Order, OrderItem
import logging

logger = logging.getLogger(__name__)

# --- 1. TABLE SERIALIZER ---
class TableSerializer(serializers.ModelSerializer):
    waiter_name = serializers.CharField(source='assigned_waiter.username', read_only=True)
    
    class Meta:
        model = Table
        fields = [
            'id', 'table_number', 'qr_id', 'qr_code_image', 'is_active', 
            'is_occupied', 'assigned_waiter', 'waiter_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'qr_id', 'created_at', 'updated_at']

# --- 2. CATEGORY SERIALIZER ---
class CategorySerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    station_display = serializers.CharField(source='get_station_display', read_only=True)
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'image', 'station', 
            'station_display', 'is_active', 'items_count', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_items_count(self, obj):
        return obj.items.filter(is_available=True).count()

# --- 2.5 MENU ITEM SERIALIZER ---
class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'category', 'category_name', 'name', 'description', 
            'price', 'image', 'is_available', 'is_ready_to_serve', 
            'prep_time', 'stock_quantity', 'tax_percent'
        ]

# --- 3. ORDER ITEM SERIALIZER (Universal for Chef & Waiter) ---

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    order = serializers.PrimaryKeyRelatedField(read_only=True) 
    order_table_no = serializers.IntegerField(source='order.table.table_number', read_only=True)
    group_tag = serializers.CharField(source='order.group_tag', read_only=True)
    station = serializers.CharField(source='menu_item.category.station', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'menu_item', 'menu_item_name', 'quantity', 
            'unit_price', 'subtotal', 'status', 'status_display', 
            'assigned_chef', 'order_table_no', 'group_tag',
            'station', 'ordered_by_name', 'created_at'
        ]

    def get_subtotal(self, obj):
        return obj.quantity * obj.unit_price



class WaiterOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField() # Custom method for filtering
    invoice_no = serializers.CharField(source='invoice_number', read_only=True)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'invoice_no', 'customer_name', 'status', 'items', 'total_amount', 'table_number']


    def get_items(self, obj):
        station = self.context.get('station')
    # 🌟 Sirf wahi items jo is station ke hain
        items = obj.items.filter(menu_item__category__station=station)
    
    # 🌟 IMPORTANT: Sirf wahi items jo KDS ke liye ready hain
    # Agar aapne DB mein 'confirmed' kiya hai, toh ye filter zaroori hai
        items = items.filter(status__in=['confirmed', 'cooking', 'ready'])
    
        print(f"DEBUG: Order {obj.id} has {items.count()} items for station {station}")
        return OrderItemSerializer(items, many=True).data
        
        
    def get_total_amount(self, obj):
        return sum(item.quantity * item.unit_price for item in obj.items.all())


class WaiterTableSerializer(serializers.ModelSerializer):
    active_orders = serializers.SerializerMethodField()
    is_occupied = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = ['id', 'table_number', 'is_occupied', 'active_orders']

    def get_active_orders(self, obj):
        # Is table ke wo orders jo paid nahi hain
        orders = Order.objects.filter(table=obj, is_paid=False)
        return WaiterOrderSerializer(orders, many=True).data

    def get_is_occupied(self, obj):
        return Order.objects.filter(table=obj, is_paid=False).exists()



# --- 4. ORDER DETAIL SERIALIZER ---
class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    table_number = serializers.IntegerField(source='table.table_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    waiter_name = serializers.CharField(source='waiter.username', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'invoice_number', 'table', 'table_number', 'group_tag',
            'customer_name', 'customer_mobile', 'order_type', 'total_amount', 
            'is_paid', 'status', 'status_display', 'waiter', 'waiter_name',
            'payment_method', 'items', 'created_at', 'paid_at'
        ]

# --- 5. ORDER CREATE SERIALIZER ---
class OrderCreateSerializer(serializers.ModelSerializer):
    items = serializers.ListField(child=serializers.DictField())
    is_waiter = serializers.BooleanField(required=False, default=False, write_only=True)
    # 🌟 Serializer mein bhi table ko optional rakhein
    table = serializers.PrimaryKeyRelatedField(queryset=Table.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Order
        fields = ['table', 'customer_name', 'customer_mobile', 'order_type', 'group_tag', 'items', 'is_waiter', 'discount_amount']

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        is_waiter_order = validated_data.pop('is_waiter', False)
        table = validated_data.get('table', None) # 👈 Table null ho sakti hai
        
        request = self.context.get('request')
        current_user = request.user if request and request.user.is_authenticated else None

        # 1. Order Object Creation
        order = Order.objects.create(
            waiter=current_user,
            **validated_data
        )

        subtotal = Decimal('0.00')

        # 2. Items Processing
        for item in items_data:
            m_item = MenuItem.objects.get(id=item['menu_item'])
            qty = int(item.get('quantity', 1))
            
            OrderItem.objects.create(
                order=order,
                menu_item=m_item,
                quantity=qty,
                unit_price=m_item.price,
                ordered_by_name=item.get('ordered_by_name', order.customer_name or "Counter"),
                status='confirmed' # Counter/Table dono confirmed
            )
            subtotal += (m_item.price * qty)

        # 3. Calculation Logic
        discount = Decimal(str(validated_data.get('discount_amount', 0) or 0))
        tax = (subtotal - discount) * Decimal('0.18')
        order.total_amount = (subtotal - discount) + tax
        order.save()

        # 4. 🌟 Table Management: Sirf tabhi occupy karein jab table ID ho
        if table:
            table.is_occupied = True
            table.save()

        return order

        
# --- 6. TABLE FLOOR MAP SERIALIZER ---
class TableFloorMapSerializer(serializers.ModelSerializer):
    active_sessions = serializers.SerializerMethodField()
    waiter_name = serializers.ReadOnlyField(source='assigned_waiter.username')

    class Meta:
        model = Table
        fields = ['id', 'table_number', 'is_occupied', 'waiter_name', 'active_sessions']

    def get_active_sessions(self, obj):
        orders = Order.objects.filter(table=obj, is_paid=False)
        return OrderDetailSerializer(orders, many=True).data

# --- 7. OTHER UTILITY SERIALIZERS ---
class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['status', 'payment_method', 'is_paid']


# --- ORDER LIST SERIALIZER (For Dashboard & History) ---
class OrderListSerializer(serializers.ModelSerializer):
    table_number = serializers.IntegerField(source='table.table_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    waiter_name = serializers.CharField(source='waiter.username', read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'invoice_number', 'table_number', 'customer_name', 
            'total_amount', 'status', 'status_display', 'is_paid', 
            'waiter_name', 'item_count', 'created_at', 'group_tag'
        ]

    def get_item_count(self, obj):
        return obj.items.count()


class OrderItemInputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1)
    seat_number = serializers.IntegerField(required=False)

class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = '__all__'

class KDSOrderTicketSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    table_no = serializers.CharField(source='table.table_number', default='N/A') # 👈 Source fail hone par N/A dega

    class Meta:
        model = Order
        fields = ['id', 'table_no', 'customer_name', 'items', 'created_at']

    def get_items(self, obj):
        station = self.context.get('station')
        
        # Filter karte waqt hum ensure karenge ki menu_item aur category null na ho
        items = obj.items.filter(
            menu_item__isnull=False,
            menu_item__category__isnull=False,
            menu_item__category__station__iexact=station,
            status__in=['confirmed', 'cooking']
        ).select_related('menu_item', 'menu_item__category')

        return [{
            "id": item.id,
            "menu_item_name": item.menu_item.name if item.menu_item else "Unknown Item",
            "quantity": item.quantity,
            "status": item.status,
        } for item in items]


class KDSIteemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.ReadOnlyField(source='menu_item.name')
    chef_name = serializers.ReadOnlyField(source='assigned_chef.username')
    assigned_chef_id = serializers.ReadOnlyField(source='assigned_chef.id')

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item_name', 'quantity', 'status', 'assigned_chef_id', 'chef_name', 'created_at']


class KDSOrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.ReadOnlyField(source='menu_item.name')
    assigned_chef_id = serializers.ReadOnlyField(source='assigned_chef.id')
    chef_name = serializers.ReadOnlyField(source='assigned_chef.username')
    station = serializers.ReadOnlyField(source='menu_item.category.station')

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item_name', 'quantity', 'status', 'assigned_chef_id', 'chef_name', 'station', 'created_at']

class KDSOrderSerializer(serializers.ModelSerializer):
    items = KDSOrderItemSerializer(many=True, read_only=True)
    table_no = serializers.ReadOnlyField(source='table.table_number')
    invoice_no = serializers.ReadOnlyField(source='invoice_number')

    class Meta:
        model = Order
        fields = ['id', 'invoice_no', 'table_no', 'items', 'created_at']

class WaiterOrderItemSerializer(serializers.ModelSerializer):
    # assigned_chef aur status display ke liye
    chef_name = serializers.CharField(source='assigned_chef.username', read_only=True, default=None)
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item_name', 'quantity', 'status', 'chef_name', 'created_at']

class WaiterOrderSerializer(serializers.ModelSerializer):
    items = WaiterOrderItemSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    invoice_no = serializers.CharField(source='invoice_number', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'invoice_no', 'customer_name', 'status', 'items', 'total_amount', 'group_tag']

class WaiterTableSerializer(serializers.ModelSerializer):
    # Sirf wahi orders jo abhi tak paid nahi hain
    active_orders = serializers.SerializerMethodField()
    total_table_amount = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = ['id', 'table_number', 'is_occupied', 'active_orders', 'total_table_amount']

    def get_active_orders(self, obj):
        orders = Order.objects.filter(table=obj, is_paid=False)
        return WaiterOrderSerializer(orders, many=True).data

    def get_total_table_amount(self, obj):
        # Saare active invoices ka total sum
        from django.db.models import Sum
        total = Order.objects.filter(table=obj, is_paid=False).aggregate(Sum('total_amount'))['total_amount__sum']
        return total or 0.00


#.................................................................................................#
#.................................................................................................#

class AdminOrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.ReadOnlyField(source='menu_item.name')
    station = serializers.ReadOnlyField(source='menu_item.category.station')

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item_name', 'quantity', 'status', 'station', 'ordered_by_name']

class AdminOrderSerializer(serializers.ModelSerializer):
    # 🌟 MAGIC LINE: Isse items ki list 'active_orders' ke andar aayegi
    # 'order_items' woh related_name hai jo aapne OrderItem model mein diya hoga
    items = AdminOrderItemSerializer(source='order_items', many=True, read_only=True)
    waiter_name = serializers.ReadOnlyField(source='waiter.username')
    
    class Meta:
        model = Order
        fields = [
            'id', 'invoice_number', 'customer_name', 'waiter_name', 
            'group_tag', 'status', 'total_amount', 'is_paid', 
            'items', 'created_at'
        ]
        
    def get_calculated_total(self, obj):
        # Items ka price calculate karke bhejega
        return sum(item.quantity * item.unit_price for item in obj.order_items.all())