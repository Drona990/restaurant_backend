from django.contrib import admin
from django.utils.html import format_html
from .models import Table, Category, MenuItem, Order, OrderItem

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('table_number', 'qr_id_short', 'is_occupied', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_occupied', 'created_at')
    search_fields = ('table_number',)
    # 🌟 updated_at tabhi chalega jab model mein migrate ho chuka ho
    readonly_fields = ('qr_id', 'created_at', 'updated_at', 'qr_code_image_preview')
    
    fieldsets = (
        ('Table Information', {
            'fields': ('table_number', 'is_active', 'is_occupied')
        }),
        ('QR Code', {
            'fields': ('qr_id', 'qr_code_image', 'qr_code_image_preview')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def qr_id_short(self, obj):
        return str(obj.qr_id)[:8]
    qr_id_short.short_description = 'QR ID'
    
    def qr_code_image_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="150" height="150"/>', obj.qr_code_image.url)
        return "No QR code generated"
    qr_code_image_preview.short_description = 'QR Code Preview'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'items_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    
    def items_count(self, obj):
        return obj.menuitem_set.count() # Fixed related name access
    items_count.short_description = 'Total Items'


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available', 'created_at')
    list_filter = ('is_available', 'category', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('unit_price', 'created_at')
    fields = ('menu_item', 'quantity', 'unit_price', 'special_instructions')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'table', 'customer_name', 'total_amount', 
                   'is_paid', 'status', 'order_type', 'created_at')
    list_filter = ('is_paid', 'status', 'order_type', 'payment_method', 'created_at')
    search_fields = ('invoice_number', 'customer_name', 'customer_mobile')
    readonly_fields = ('invoice_number', 'total_amount', 'created_at', 'updated_at', 'paid_at')
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('invoice_number', 'table', 'status', 'order_type')
        }),
        ('Customer Details', {
            'fields': ('customer_name', 'customer_mobile')
        }),
        ('Payment', {
            'fields': ('total_amount', 'discount_amount', 'is_paid', 'payment_method', 'paid_at')
        }),
        ('Additional', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj: # Lock critical fields after order is placed
            return self.readonly_fields + ('table', 'customer_name', 'order_type')
        return self.readonly_fields