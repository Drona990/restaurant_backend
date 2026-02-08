from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from django.utils import timezone
import random, string


from restaurant_core.models import Discount
from restaurant_core.serializers import DiscountSerializer

class DiscountViewSet1(viewsets.ModelViewSet):
    queryset = Discount.objects.all().order_by('-id')
    serializer_class = DiscountSerializer

    @action(detail=False, methods=['post'])
    def apply_discount(self, request):
        """
        Billing Logic: Pick the best active discount
        Body: {"subtotal": 5000, "coupon_code": "WELCOME10"}
        """
        subtotal = Decimal(request.data.get('subtotal', 0))
        user_coupon = request.data.get('coupon_code', None)
        now = timezone.now()

        # Fetch Candidates
        threshold = Discount.objects.filter(
            discount_type='THRESHOLD', is_active=True, min_purchase__lte=subtotal
        ).order_by('-min_purchase').first()

        festival = Discount.objects.filter(
            discount_type='FESTIVAL', is_active=True, 
            valid_from__lte=now, valid_to__gte=now, min_purchase__lte=subtotal
        ).first()

        coupon = None
        if user_coupon:
            coupon = Discount.objects.filter(
                discount_type='COUPON', code=user_coupon, is_active=True, min_purchase__lte=subtotal
            ).first()

        # Calculation logic
        def get_discount_amt(disc):
            if disc.value_type == 'PERCENT':
                return subtotal * (disc.value / Decimal('100'))
            return disc.value

        options = []
        if threshold: options.append({'amt': get_discount_amt(threshold), 'obj': threshold})
        if festival: options.append({'amt': get_discount_amt(festival), 'obj': festival})
        if coupon: options.append({'amt': get_discount_amt(coupon), 'obj': coupon})

        if not options:
            return Response({"discount_amount": 0, "applied_offer_name": "No Offer"})

        # Winner is the one with highest discount value
        best = max(options, key=lambda x: x['amt'])

        return Response({
            "discount_amount": float(best['amt']),
            "applied_offer_name": best['obj'].name,
            "discount_type": best['obj'].discount_type,
            "code": best['obj'].code if best['obj'].code else "AUTO"
        })

    @action(detail=False, methods=['get'])
    def generate_code(self, request):
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return Response({'code': code})
    


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all().order_by('-id')
    serializer_class = DiscountSerializer

    @action(detail=False, methods=['get'])
    def generate_code(self, request):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return Response({'code': code})

    @action(detail=False, methods=['post'])
    def apply_discount(self, request):
        subtotal = Decimal(str(request.data.get('subtotal', 0)))
        user_coupon = request.data.get('coupon_code', None)
        now = timezone.now()
        
        error_message = None

        # 1. 🔍 Threshold & Festival (Auto-apply candidates)
        threshold = Discount.objects.filter(
            discount_type='THRESHOLD', is_active=True, min_purchase__lte=subtotal
        ).order_by('-min_purchase').first()

        festival = Discount.objects.filter(
            discount_type='FESTIVAL', is_active=True, 
            valid_from__lte=now, valid_to__gte=now, min_purchase__lte=subtotal
        ).first()

        # 2. 🎫 Coupon Validation (Manual entry)
        coupon = None
        if user_coupon:
            coupon_obj = Discount.objects.filter(discount_type='COUPON', code__iexact=user_coupon).first()
            
            if not coupon_obj:
                error_message = "Invalid Coupon Code"
            elif not coupon_obj.is_active:
                error_message = "This coupon is no longer active"
            elif subtotal < coupon_obj.min_purchase:
                error_message = f"Min purchase for this coupon is Rs.{coupon_obj.min_purchase}"
            elif coupon_obj.valid_from and now < coupon_obj.valid_from:
                error_message = "Offer starts soon!"
            elif coupon_obj.valid_to and now > coupon_obj.valid_to:
                error_message = "Coupon Expired"
            else:
                coupon = coupon_obj # Sab sahi hai!

        # 3. Calculation Helper
        def get_discount_amt(disc):
            if disc.value_type == 'PERCENT':
                return (subtotal * (disc.value / Decimal('100'))).quantize(Decimal('0.01'))
            return disc.value

        options = []
        if threshold: options.append({'amt': get_discount_amt(threshold), 'obj': threshold})
        if festival: options.append({'amt': get_discount_amt(festival), 'obj': festival})
        if coupon: options.append({'amt': get_discount_amt(coupon), 'obj': coupon})

        # 4. Result Logic
        if not options:
            return Response({
                "success": False,
                "discount_amount": 0, 
                "applied_offer_name": "No Offer",
                "message": error_message or "No eligible offers found"
            }, status=status.HTTP_200_OK if not error_message else status.HTTP_400_BAD_REQUEST)

        # Winner is the one with highest discount value
        best = max(options, key=lambda x: x['amt'])

        return Response({
            "success": True,
            "discount_amount": float(best['amt']),
            "applied_offer_name": best['obj'].name,
            "discount_type": best['obj'].discount_type,
            "code": best['obj'].code if best['obj'].code else "AUTO",
            "message": "Coupon Applied Successfully!" if coupon and best['obj'] == coupon else None
        })