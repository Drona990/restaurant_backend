"""
Utility functions for the restaurant app.
"""
import logging
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from decimal import Decimal

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from restaurant_core.models import Discount


logger = logging.getLogger(__name__)


class APIResponse:
    """Standard API response structure."""
    
    @staticmethod
    def success(data=None, message="Request successful", status_code=status.HTTP_200_OK):
        """Return successful response."""
        return Response(
            {
                "success": True,
                "message": message,
                "data": data,
            },
            status=status_code
        )
    
    @staticmethod
    def error(message="An error occurred", error_code="ERROR", 
              status_code=status.HTTP_400_BAD_REQUEST, details=None):
        """Return error response."""
        response_data = {
            "success": False,
            "message": message,
            "error_code": error_code,
        }
        if details:
            response_data["details"] = details
        
        return Response(response_data, status=status_code)
    
    @staticmethod
    def validation_error(errors, message="Validation failed"):
        """Return validation error response."""
        return Response(
            {
                "success": False,
                "message": message,
                "error_code": "VALIDATION_ERROR",
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @staticmethod
    def paginated_success(data, total, page, page_size, message="Request successful"):
        """Return paginated success response."""
        return Response(
            {
                "success": True,
                "message": message,
                "data": data,
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size,
                }
            },
            status=status.HTTP_200_OK
        )


class RestaurantException(Exception):
    """Base exception for restaurant app."""
    
    def __init__(self, message, error_code="RESTAURANT_ERROR", status_code=400):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)


class OrderNotFoundException(RestaurantException):
    """Raised when order is not found."""
    
    def __init__(self, order_id):
        super().__init__(
            f"Order with id {order_id} not found",
            "ORDER_NOT_FOUND",
            404
        )


class TableNotFoundException(RestaurantException):
    """Raised when table is not found."""
    
    def __init__(self, table_id):
        super().__init__(
            f"Table with id {table_id} not found",
            "TABLE_NOT_FOUND",
            404
        )


class InvalidOrderStatusException(RestaurantException):
    """Raised when invalid order status transition is attempted."""
    
    def __init__(self, current_status, new_status):
        super().__init__(
            f"Cannot transition from {current_status} to {new_status}",
            "INVALID_STATUS_TRANSITION",
            400
        )


def log_error(view_name, error_message, exception=None):
    """Log errors with context."""
    log_message = f"[{view_name}] {error_message}"
    if exception:
        log_message += f" - {str(exception)}"
    logger.error(log_message)



def calculate_best_discount(subtotal, user_coupon=None):
    now = timezone.now()
    best_discount_amount = Decimal('0.00')
    applied_name = "No Discount"

    # 1. Sabse pehle "THRESHOLD" (Purchase Upto) check karein
    # Isme hum dekhte hain ki kya subtotal min_purchase se zyada hai
    threshold_disc = Discount.objects.filter(
        discount_type='THRESHOLD',
        is_active=True,
        min_purchase__lte=subtotal
    ).order_by('-min_purchase').first() # Sabse bada threshold pakdein

    # 2. Phir "FESTIVAL" check karein
    festival_disc = Discount.objects.filter(
        discount_type='FESTIVAL',
        is_active=True,
        valid_from__lte=now,
        valid_to__gte=now,
        min_purchase__lte=subtotal
    ).first()

    # 3. Last mein "COUPON" check karein (Agar user ne diya hai)
    coupon_disc = None
    if user_coupon:
        coupon_disc = Discount.objects.filter(
            discount_type='COUPON',
            code=user_coupon,
            is_active=True,
            min_purchase__lte=subtotal
        ).first()

    # Calculation Helper
    def get_amt(disc, amt):
        if disc.value_type == 'PERCENT':
            return amt * (disc.value / Decimal('100'))
        return disc.value

    # Logic: System automatic best discount choose karega
    results = []
    if threshold_disc: results.append((get_amt(threshold_disc, subtotal), threshold_disc.name))
    if festival_disc: results.append((get_amt(festival_disc, subtotal), festival_disc.name))
    if coupon_disc: results.append((get_amt(coupon_disc, subtotal), f"Coupon: {coupon_disc.code}"))

    if results:
        # Sabse zyada discount dene wala choose karein
        best_discount_amount, applied_name = max(results, key=lambda x: x[0])

    return {
        "discount_amount": best_discount_amount,
        "applied_offer": applied_name
    }



def broadcast_order_update(station, table_no, notify_type, message, data=None):
    """
    station: 'kitchen', 'bar', 'both', 'waiter_only'
    notify_type: 'NEW_TICKET', 'KDS_REFRESH', 'STATUS_UPDATE'
    """
    channel_layer = get_channel_layer()
    
    # 📦 Flutter ko bhejne wala actual data
    payload = {
        "notification_type": notify_type,
        "message": message,
        "data": data or {}
    }

    # 🎯 Target Groups ki list decide karna
    targets = []

    # 1. NEW FOOD ORDER: Chef + Waiter + Customer (Admin is already in these groups)
    if station == 'kitchen':
        targets = ['kitchen_group', 'waiters_group', f'table_{table_no}']
    
    # 2. NEW DRINK ORDER: Barman + Waiter + Customer
    elif station == 'bar':
        targets = ['bar_group', 'waiters_group', f'table_{table_no}']
    
    # 3. KITCHEN READY: Waiter aur Customer ko notify karo (Chef refresh ke liye kitchen_group bhi)
    elif station == 'kitchen_ready':
        targets = ['kitchen_group', 'waiters_group', f'table_{table_no}']

    # 4. BAR READY: Waiter aur Customer ko notify karo (Barman refresh ke liye bar_group bhi)
    elif station == 'bar_ready':
        targets = ['bar_group', 'waiters_group', f'table_{table_no}']

    # 5. GENERAL UPDATES: Sabko refresh karna ho (Like Bill Paid, Cancelled)
    elif station == 'both':
        targets = ['kitchen_group', 'bar_group', 'waiters_group', f'table_{table_no}']

    # 6. WAITER ONLY: Sirf waiter ko (Like Bill Request)
    elif station == 'waiter_only':
        targets = ['waiters_group', f'table_{table_no}']

    # 🚀 Loop chala kar sirf relevant groups ko message bhejien
    unique_targets = list(set(targets)) # Double messages hatane ke liye
    for group in unique_targets:
        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "order_notification", # Consumer ke method se match hona chahiye
                "payload": payload
            }
        )
