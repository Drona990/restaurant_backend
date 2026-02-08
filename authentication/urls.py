from django.urls import path
from .views import *

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/check-username/", CheckUsernameAvailability.as_view()),
    path("signup/send-otp/", SendSignupOTP.as_view()),
    path("signup/verify-otp/", VerifySignupOTP.as_view()),
    path("signup/complete/", CompleteSignup.as_view()),
    path("auth/login/", LoginView.as_view()),

    path('forgot-password/send-otp/', ForgotPasswordSendOTPView.as_view()),
    path('forgot-password/verify-otp/', ForgotPasswordVerifyOTPView.as_view()),
    path('forgot-password/reset/', ForgotPasswordResetView.as_view()),

    # ===== ROLE-BASED MANAGEMENT =====
    # Superuser endpoint
    path('superuser/create/', CreateFirstSuperuserView.as_view(), name='create-superuser'),
    
    # Superuser endpoints
    path('admin/create/', CreateAdminView.as_view(), name='create-admin'),
    path('admin/list/', ListAdminsView.as_view(), name='list-admins'),

    # Admin endpoints - staff management
    path('staff/create/', CreateStaffView.as_view(), name='create-staff'),
    path('staff/list/', ListStaffView.as_view(), name='list-staff'),
    path('staff/<uuid:staff_id>/deactivate/', DeactivateStaffView.as_view(), name='deactivate-staff'),
    path('staff/<uuid:staff_id>/activate/', ActivateStaffView.as_view(), name='activate-staff'),

    # Dashboard
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    path('user/update-fcm-token/', UpdateFCMTokenView.as_view(), name='update-fcm'),
    path('user/dashboard/', UserDashboardView.as_view(), name='user-dashboard'),

]
