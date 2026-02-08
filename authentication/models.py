import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('superuser', 'Superuser'),
        ('admin', 'Admin/Manager'),
        ('staff', 'Restaurant Staff'),
        ('chef', 'Kitchen Chef'),
        ('barman', 'Bar Specialist'),
        ('waiter', 'Restaurant Waiter'),

    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)

    name = models.CharField(max_length=255, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')
    fcm_token = models.TextField(null=True, blank=True, help_text="Token for Push Notifications")
    is_on_duty = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users',
        help_text="Admin who created this user"
    )

    is_verified = models.BooleanField(default=False)
    is_password_set = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(email__isnull=False) | Q(phone_number__isnull=False),
                name="email_or_phone_required",
            )
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    

class RecoveryContact(models.Model):
    CONTACT_TYPE_CHOICES = (
        ("email", "Email"),
        ("phone", "Phone"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="recovery_contacts"
    )
    contact_type = models.CharField(max_length=10, choices=CONTACT_TYPE_CHOICES)
    contact_value = models.CharField(max_length=255, unique=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "contact_value")

    def __str__(self):
        return f"{self.user.username} - {self.contact_value}"


class OTP(models.Model):
    PURPOSE_CHOICES = (
        ("signup", "Signup"),
        ("password_reset", "Password Reset"),
        ("recovery_verify", "Recovery Verify"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)

    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)


