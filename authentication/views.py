from django.db.models import Q
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from core.permissions import IsAdminOrSuperuser, IsSuperuser
from restaurant_core.models import Order, Table
from .models import CustomUser, OTP, RecoveryContact
from .serializers import *
from .utils.otp import generate_otp
from .utils.email import send_otp_email
from .utils.response import success_response, error_response
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from django.utils import timezone

# ===== ROLE-BASED PERMISSION CLASSES =====

class HealthCheckView(APIView):
    authentication_classes = [] 
    permission_classes = [] 

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "message": "Restaurant backend is running 🚀"
            },
            status=status.HTTP_200_OK
        )

# ===== ROLE MANAGEMENT VIEWS =====

class CreateFirstSuperuserView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if CustomUser.objects.filter(role='superuser').exists():
            return error_response(
                "Superuser already exists. Cannot create another.",
                403
            )

        serializer = CreateSuperuserSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors, 400)

        email = serializer.validated_data['email']
        
        # Generate username from email
        username = email.split('@')[0]
        counter = 1
        original_username = username
        while CustomUser.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1

        user = CustomUser.objects.create_superuser(
            username=username,
            email=email,
            password=serializer.validated_data['password'],
            role='superuser',
            is_verified=True,
            is_password_set=True,
        )

        return success_response(
            "Superuser created successfully",
            data={
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "message": "You can now login and create admin accounts"
            },
            status_code=201
        )


class CreateAdminView(APIView):
    permission_classes = [IsSuperuser]

    def post(self, request):
        serializer = CreateAdminSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors, 400)

        email = serializer.validated_data['email']
        username = email.split('@')[0] 
        
        # Ensure username uniqueness
        counter = 1
        original_username = username
        while CustomUser.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=serializer.validated_data['password'],
            name=serializer.validated_data.get('name', ''),
            role='admin',
            created_by=request.user,
            is_verified=True,
            is_password_set=True,
        )

        if user.email:
            RecoveryContact.objects.create(
                user=user,
                contact_type="email",
                contact_value=user.email,
                is_verified=True
            )

        return success_response(
            "Admin created successfully",
            data={
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "message": f"Login with email: {user.email} and provided password"
            },
            status_code=201
        )


class CreateStaffView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        print(f"DEBUG: Incoming Request Data: {request.data}")
        serializer = CreateStaffSerializer(data=request.data)
        if not serializer.is_valid():
            print(f"❌ SERIALIZER ERRORS: {serializer.errors}") # 👈 Ye terminal mein asali wajah batayega
            return error_response(serializer.errors, 400)

        # 1. ✅ Request se Role uthaiye (Default 'staff' rakhein)
        # Body: {"email": "...", "password": "...", "role": "chef"}
        requested_role = request.data.get('role', 'staff')
        print(f"DEBUG: Requested Role: {requested_role}")

        # 2. ✅ Validation: Admin superuser ya admin create na kar paye
        allowed_roles = ['staff', 'chef', 'barman','waiter']
        if requested_role not in allowed_roles:
            print(f"DEBUG: Role {requested_role} rejected. Not in {allowed_roles}")
            return error_response(f"You can only create: {allowed_roles}", 400)

        email = serializer.validated_data['email']
        username = email.split('@')[0]
        
        counter = 1
        original_username = username
        while CustomUser.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1

        # 3. ✅ Use requested_role instead of hardcoded 'staff'
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=serializer.validated_data['password'],
            name=serializer.validated_data.get('name', ''),
            role=requested_role, # Dynamic role yahan aayega
            created_by=request.user,
            is_verified=True,
            is_password_set=True,
        )

        if user.email:
            RecoveryContact.objects.create(
                user=user,
                contact_type="email",
                contact_value=user.email,
                is_verified=True
            )

        return success_response(
            f"{requested_role.capitalize()} created successfully",
            data={
                "user_id": str(user.id),
                "username": user.username,
                "role": user.role,
                "message": f"Login with email: {user.email}"
            },
            status_code=201
        )


class ListStaffView(APIView):
    """Admin/Superuser views members created by them"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        """List all users created by this admin, regardless of role"""
        if request.user.role == 'superuser':
            # Superuser ko sabhi dikhen (except other superusers)
            staff = CustomUser.objects.exclude(role='superuser')
        else:
            # Admin ko wahi dikhen jo usne create kiye hain
            # Yahan role='staff' filter hataya gaya hai taaki Chef/Barman bhi dikhen
            staff = CustomUser.objects.filter(created_by=request.user)

        data = [
            {
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "name": user.name,
                "dob": user.dob,
                "gender": user.gender,
                "is_active": user.is_active,
                "created_at": user.date_joined,
                "role": user.role,  # Frontend filter ke liye ye zaroori hai
            }
            for user in staff
        ]

        return success_response(
            "Staff list retrieved",
            data=data
        )


class ListAdminsView(APIView):
    """Superuser views all admins"""
    permission_classes = [IsSuperuser]

    def get(self, request):
        """List all admins"""
        admins = CustomUser.objects.filter(role='admin')

        data = [
            {
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "name": user.name,
                "is_active": user.is_active,
                "staff_count": user.created_users.filter(role='staff').count(),
                "created_at": user.date_joined
            }
            for user in admins
        ]

        return success_response(
            "Admins list retrieved",
            data=data
        )


class DeactivateStaffView(APIView):
    """Admin deactivates staff"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, staff_id):
        """Deactivate staff member"""
        try:
            staff = CustomUser.objects.get(id=staff_id, role='staff')
        except CustomUser.DoesNotExist:
            return error_response("Staff not found", 404)

        # Check if admin owns this staff
        if request.user.role == 'admin' and staff.created_by != request.user:
            return error_response("You can only deactivate your own staff", 403)

        staff.is_active = False
        staff.save()

        return success_response(
            "Staff deactivated successfully",
            data={"user_id": str(staff.id), "is_active": staff.is_active}
        )

class ActivateStaffView(APIView):
    """Admin activates staff"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, staff_id):
        """Activate staff member"""
        try:
            staff = CustomUser.objects.get(id=staff_id, role='staff')
        except CustomUser.DoesNotExist:
            return error_response("Staff not found", 404)

        # Check if admin owns this staff
        if request.user.role == 'admin' and staff.created_by != request.user:
            return error_response("You can only activate your own staff", 403)

        staff.is_active = True
        staff.save()

        return success_response(
            "Staff activated successfully",
            data={"user_id": str(staff.id), "is_active": staff.is_active}
        )

class UpdateProfileView(APIView):
    """User updates their profile after login"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        """
        Update user profile
        Body: {
            "name": "Full Name",
            "dob": "1990-01-15",
            "gender": "Male"
        }
        """
        serializer = UpdateProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors, 400)

        user = request.user
        
        if 'name' in serializer.validated_data:
            user.name = serializer.validated_data['name']
        
        if 'dob' in serializer.validated_data:
            user.dob = serializer.validated_data['dob']
        
        if 'gender' in serializer.validated_data:
            user.gender = serializer.validated_data['gender']
        
        user.save()

        return success_response(
            "Profile updated successfully",
            data={
                "user_id": str(user.id),
                "email": user.email,
                "name": user.name,
                "dob": user.dob,
                "gender": user.gender,
                "role": user.role
            }
        )
    
    
class UpdateFCMTokenView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        token = request.data.get('fcm_token')
        request.user.fcm_token = token
        request.user.save()
        return Response({"status": "success", "message": "FCM Token Updated"})



class UserDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            today = timezone.now().date()
            
            # 1. Role Detection
            role = 'superuser' if user.is_superuser else getattr(user, 'role', 'staff')
            if not role: role = 'staff'

            data = {
                "user": {
                    "username": user.username,
                    "user_id": user.id,
                    "role": role,
                    "name": getattr(user, 'name', user.username) or user.username,
                    "fcm_status": bool(getattr(user, 'fcm_token', None))
                }
            }

            # --- OWNER / SUPERUSER ---
            if role == 'superuser':
                # ✅ Filter changed to 'completed' or 'is_paid=True' as per your model
                revenue_query = Order.objects.filter(is_paid=True, created_at__date=today).aggregate(res=Sum('total_amount'))
                revenue = revenue_query['res'] or 0.0
                
                data["stats"] = {
                    "total_admins": CustomUser.objects.filter(role='admin').count(),
                    "total_staff": CustomUser.objects.exclude(role__in=['superuser', 'admin']).count(),
                    "daily_revenue": float(revenue),
                    "active_tables": Table.objects.filter(is_occupied=True).count()
                }

            # --- ADMIN / MANAGER ---
            elif role == 'admin':
                staff_qs = CustomUser.objects.filter(role__in=['waiter', 'chef', 'barman'])
                data["stats"] = {
                    "total_staff": staff_qs.count(),
                    "active_tables": Table.objects.filter(is_occupied=True).count(),
                    "total_orders_today": Order.objects.filter(created_at__date=today).count()
                }

            # --- CHEF (Kitchen) ---
            elif role == 'chef':
                # 🌟 FIX: Station based filtering (Model path: Order -> OrderItem -> MenuItem -> Category -> Station)
                k_orders = Order.objects.filter(
                    items__menu_item__category__station='kitchen',
                    created_at__date=today
                ).distinct()
                
                data["kitchen_stats"] = {
                    "pending_orders": k_orders.filter(status='preparing').count(), # Model choice is 'preparing'
                    "ready_to_serve": k_orders.filter(status='ready').count(),
                    "completed_today": k_orders.filter(status='served').count()
                }

            # --- BARMAN (Bar) ---
            elif role == 'barman':
                # 🌟 FIX: Station based filtering for Bar
                b_orders = Order.objects.filter(
                    items__menu_item__category__station='bar',
                    created_at__date=today
                ).distinct()
                
                data["bar_stats"] = {
                    "pending_drinks": b_orders.filter(status='preparing').count(),
                    "ready_now": b_orders.filter(status='ready').count(),
                    "completed_today": b_orders.filter(status='served').count()
                }

            # --- WAITERS / STAFF ---
            else:
                assigned_tables = Table.objects.filter(assigned_waiter=user, is_occupied=True)
                data["my_tasks"] = {
                    "assigned_tables_count": assigned_tables.count(),
                    "active_orders": Order.objects.filter(waiter=user, is_paid=False).count()
                }

            return Response({
                "success": True,
                "data": data
            }, status=200)

        except Exception as e:
            print(f"--- DASHBOARD ERROR: {str(e)} ---")
            return Response({"success": False, "message": str(e)}, status=500)


class CheckUsernameAvailability(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckUsernameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exists = CustomUser.objects.filter(
            username__iexact=serializer.validated_data["username"]
        ).exists()

        return success_response(
            "Username availability checked",
            data={"available": not exists}
        )


# ---------- SIGNUP FLOW ----------

class SendSignupOTP(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = generate_otp()

        OTP.objects.update_or_create(
            email=request.data.get("email"),
            phone_number=request.data.get("phone_number"),
            purpose="signup",
            defaults={"otp": otp, "verified": False}
        )

        if request.data.get("email"):
            send_otp_email(request.data["email"], otp)

        return success_response("OTP sent successfully")

class VerifySignupOTP(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email") or None
        phone = serializer.validated_data.get("phone_number") or None
        otp = serializer.validated_data["otp"]

        query = Q(otp=otp, purpose="signup")

        if email:
            query &= Q(email=email)
        elif phone:
            query &= Q(phone_number=phone)
        else:
            return error_response("Email or phone required", 400)

        otp_obj = OTP.objects.filter(query).first()

        if not otp_obj:
            return error_response("Invalid OTP", 400)

        if otp_obj.is_expired():
            otp_obj.delete()
            return error_response("OTP expired", 400)

        otp_obj.verified = True
        otp_obj.save()

        return success_response("OTP verified")


class CompleteSignup(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CompleteSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp_obj = OTP.objects.filter(
            verified=True,
            purpose="signup"
        ).filter(
            Q(email=serializer.validated_data.get("email")) |
            Q(phone_number=serializer.validated_data.get("phone_number"))
        ).first()

        if not otp_obj:
            return error_response("OTP not verified")

        user = CustomUser.objects.create_user(
            username=serializer.validated_data["username"],
            email=serializer.validated_data.get("email"),
            phone_number=serializer.validated_data.get("phone_number"),
            password=serializer.validated_data["password"],
            is_verified=True,
            is_password_set=True,
        )

        # Save as recovery contact
        if user.email:
            RecoveryContact.objects.create(
                user=user,
                contact_type="email",
                contact_value=user.email,
                is_verified=True
            )

        if user.phone_number:
            RecoveryContact.objects.create(
                user=user,
                contact_type="phone",
                contact_value=user.phone_number,
                is_verified=True
            )

        otp_obj.delete()

        refresh = RefreshToken.for_user(user)
        return success_response(
            "Signup completed",
            data={
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }
        )


# ---------- LOGIN ----------

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user = authenticate(
            request,
            username=request.data.get("login"),
            password=request.data.get("password")
        )

        if not user:
            return error_response("Invalid credentials", 401)

        refresh = RefreshToken.for_user(user)
        return success_response(
            "Login successful",
            data={
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }
        )


# ---------- FORGOT PASSWORD ----------

class ForgotPasswordSendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        recovery = RecoveryContact.objects.filter(
            contact_value=serializer.validated_data["contact"],
            is_verified=True
        ).select_related("user").first()

        if recovery:
            otp = generate_otp()
            OTP.objects.create(
                user=recovery.user,
                otp=otp,
                purpose="password_reset"
            )

            if recovery.contact_type == "email":
                send_otp_email(recovery.contact_value, otp)

        return success_response("If contact exists, OTP sent")


class ForgotPasswordVerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact = serializer.validated_data["contact"]
        otp_input = serializer.validated_data["otp"]

        recovery = RecoveryContact.objects.filter(
            contact_value=contact,
            is_verified=True
        ).select_related("user").first()

        if not recovery:
            return error_response("Invalid contact", status_code=400)

        otp_obj = OTP.objects.filter(
            user=recovery.user,
            otp=otp_input,
            purpose="password_reset",
            verified=False
        ).first()

        if not otp_obj:
            return error_response("Invalid OTP", status_code=400)

        if otp_obj.is_expired():
            otp_obj.delete()
            return error_response("OTP expired", status_code=400)

        otp_obj.verified = True
        otp_obj.save()

        return success_response("OTP verified successfully")

class ForgotPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp_obj = OTP.objects.filter(
            otp=serializer.validated_data["otp"],
            purpose="password_reset",
            verified=True
        ).first()

        if not otp_obj or otp_obj.is_expired():
            return error_response("Invalid or expired OTP", status_code=400)

        user = otp_obj.user
        user.set_password(serializer.validated_data["new_password"])
        user.is_password_set = True
        user.save()

        otp_obj.delete()

        return success_response("Password reset successful")
