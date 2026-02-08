import uuid
from django.conf import settings
import qrcode
import logging
from io import BytesIO
from django.core.files import File
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone
from authentication.models import CustomUser
logger = logging.getLogger(__name__)


class Category(models.Model):
    STATION_CHOICES = [
        ('kitchen', 'Main Kitchen'),
        ('bar', 'Bar / Drinks'),
        ('pantry', 'Pantry / Snacks'),
        ('tandoor', 'Tandoor / Grill'),
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='categories/')
    # Konsa chef ya barman ise dekhega
    station = models.CharField(max_length=20, choices=STATION_CHOICES, default='kitchen')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} ({self.get_station_display()})"

class MenuItem(models.Model):
    category = models.ForeignKey(Category, related_name='items', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='menu/')
    
    # --- Future Proof Logic ---
    is_ready_to_serve = models.BooleanField(default=False) 
    prep_time = models.PositiveIntegerField(default=15)  
    stock_quantity = models.IntegerField(default=-1) 
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5.0)
    
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} - {self.category.name}"


class Table(models.Model):
    table_number = models.PositiveIntegerField(unique=True)
    qr_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_code_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_occupied = models.BooleanField(default=False) # 🌟 Multi-session check ke liye
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_waiter = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['table_number']

    def save(self, *args, **kwargs):
        if not self.qr_code_image:
            qr_content = f"https://your-app.web.app/#/order?table_id={self.qr_id}"
            qr_img = qrcode.make(qr_content)
            canvas = BytesIO()
            qr_img.save(canvas, format='PNG')
            self.qr_code_image.save(f"table_{self.table_number}.png", File(canvas), save=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Table {self.table_number}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('awaiting_payment', 'Awaiting Payment'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Serving'),
        ('served', 'Served'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    ORDER_TYPE = [('prepaid', 'Prepaid'), ('postpaid', 'Postpaid')]

    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    customer_name = models.CharField(max_length=100)
    customer_mobile = models.CharField(max_length=15, blank=True, null=True)
    
    # 🌟 CORE SYSTEM FIELDS
    order_type = models.CharField(max_length=10, choices=ORDER_TYPE, default='postpaid')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preparing')
    
    payment_method = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    discount_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        null=True, 
        blank=True
    )
    group_tag = models.CharField(max_length=50, default="Group A") 
    waiter = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_waiter')

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        if self.is_paid and not self.paid_at:
            self.paid_at = timezone.now()
        super().save(*args, **kwargs)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey('MenuItem', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    ITEM_STATUS = [
    ('pending', 'Pending Approval'), 
    ('confirmed', 'Confirmed'),     
    ('cooking', 'Cooking'),         
    ('ready', 'Ready to Serve'),             
    ('served', 'Served'),          
]
    assigned_chef = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_tasks'
    )
    status = models.CharField(max_length=20, choices=ITEM_STATUS, default='pending')
    ordered_by_name = models.CharField(max_length=100, blank=True, null=True) 
    seat_number = models.PositiveIntegerField(default=1)
    share_with_seats = models.CharField(max_length=50, blank=True, null=True)
    
    @property
    def station(self):
        return self.menu_item.category.station

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name} for {self.ordered_by_name or 'Table'}"


class GuestSession(models.Model):
    """
    Yeh individual guest ki session hai (chahe mobile se ho ya manual).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # 🌟 Sabse important: Shared billing ke liye Order se link
    order = models.ForeignKey(
        Order, 
        on_delete=models.CASCADE, 
        related_name='sessions',
        null=True, 
        blank=True
    )
    
    table_number = models.IntegerField()
    seat_number = models.IntegerField(null=True, blank=True)
    guest_name = models.CharField(max_length=100, default="Guest")
    guest_fcm_token = models.TextField(null=True, blank=True)
    
    # Metadata
    is_active = models.BooleanField(default=True, help_text="False when guest leaves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Prevention: Ek hi seat par ek waqt mein do active guest nahi ho sakte
        constraints = [
            models.UniqueConstraint(
                fields=['table_number', 'seat_number', 'is_active'],
                condition=models.Q(is_active=True),
                name='unique_active_guest_per_seat'
            )
        ]

    def __str__(self):
        return f"{self.guest_name} (Table {self.table_number} - Seat {self.seat_number})"


class Discount(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('THRESHOLD', 'Purchase Upto (Auto)'),
        ('FESTIVAL', 'Festival Special (Auto)'),
        ('COUPON', 'Coupon Code (Manual)'),
    ]
    
    VALUE_TYPE_CHOICES = [
        ('PERCENT', 'Percentage (%)'),
        ('FLAT', 'Flat Amount (₹)'),
    ]

    name = models.CharField(max_length=100)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    value_type = models.CharField(max_length=10, choices=VALUE_TYPE_CHOICES, default='PERCENT')
    value = models.DecimalField(max_digits=10, decimal_places=2)
    
    code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.discount_type})"