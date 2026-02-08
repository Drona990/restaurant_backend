from rest_framework import serializers
from .models import CustomUser


class CheckUsernameSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


class SignupSendOTPSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False)

    def validate(self, data):
        if not data.get("email") and not data.get("phone_number"):
            raise serializers.ValidationError("Email or phone number required")
        if CustomUser.objects.filter(username=data["username"]).exists():
            raise serializers.ValidationError("Username already exists")
        return data


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False)
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        if not data.get("email") and not data.get("phone_number"):
            raise serializers.ValidationError(
                "Email or phone number is required"
            )
        return data

class CompleteSignupSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False)
    password = serializers.CharField(min_length=6)

    name = serializers.CharField(required=False)
    dob = serializers.DateField(required=False)
    gender = serializers.CharField(required=False)


class ForgotPasswordSendOTPSerializer(serializers.Serializer):
    contact = serializers.CharField()


# ===== ROLE-BASED SERIALIZERS =====

class CreateSuperuserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value


class CreateAdminSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    name = serializers.CharField(required=False)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value


class CreateStaffSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    name = serializers.CharField(required=False)
    role = serializers.CharField(required=False) # 👈 Ye field add karna zaruri hai

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value


class UpdateProfileSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    dob = serializers.DateField(required=False)
    gender = serializers.CharField(required=False)

class ForgotPasswordVerifyOTPSerializer(serializers.Serializer):
    contact = serializers.CharField()
    otp = serializers.CharField(max_length=6)


class ForgotPasswordResetSerializer(serializers.Serializer):
    contact = serializers.CharField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=6)
