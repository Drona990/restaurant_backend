from rest_framework.permissions import IsAuthenticated

class IsSuperuser(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and getattr(request.user, 'role', None) == 'superuser'


class IsAdminOrSuperuser(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and getattr(request.user, 'role', None) in ['admin', 'superuser']


class IsStaffOrHigher(IsAuthenticated):
    def has_permission(self, request, view):
        # Pehle check karo ki user login hai ya nahi
        is_authenticated = super().has_permission(request, view)
        if not is_authenticated:
            return False
            
        # Role check (Ensure these match your User model roles)
        user_role = getattr(request.user, 'role', None)
        return user_role in ['waiter', 'admin', 'superuser']