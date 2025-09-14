from rest_framework import serializers
from .models import CustomUser, College
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken


class CollegeSerializer(serializers.ModelSerializer):
    class Meta:
        model = College
        fields = ['id', 'name', 'code', 'domain']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    college_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[('student', 'Student'), ('alumni', 'Alumni'), ('admin', 'Admin')])
    roll_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = (
            'username', 'email', 'password', 'phone',
            'role', 'college_code', 'linkedin_url', 'roll_number'
        )

    def validate(self, attrs):
        role = attrs.get("role")
        roll_number = attrs.get("roll_number")

        # Roll number required for Student/Alumni
        if role in ["student", "alumni"] and not roll_number:
            raise serializers.ValidationError("Roll number is required for Students and Alumni.")

        return attrs

    def validate_college_code(self, value):
        if value:
            try:
                College.objects.get(code=value)
            except College.DoesNotExist:
                raise serializers.ValidationError("College code invalid")
        return value

    def create(self, validated_data):
        college_code = validated_data.pop('college_code', None)
        roll_number = validated_data.pop('roll_number', None)
        college = None
        if college_code:
            college = College.objects.get(code=college_code)

        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.college = college
        if roll_number:
            user.roll_number = roll_number

        user.set_password(password)

        # Admin email restriction
        if user.role == "admin":
            if not college or not college.domain:
                raise serializers.ValidationError("Admin registration requires a valid college with a domain.")
            if not user.email.endswith(f"@{college.domain}"):
                raise serializers.ValidationError(f"Admins must register with official college email (@{college.domain}).")
            user.verified = True
            user.is_approved = True  # Admins auto-approved

        # Auto-verify for Students/Alumni if email domain matches
        elif user.role in ["student", "alumni"]:
            if college and college.domain and user.email.endswith(f"@{college.domain}"):
                user.verified = True
            user.is_approved = False  # Wait for admin approval
            user.is_active = False    # Prevent login until approval

        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")

        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials")

        # Block login until approved
        if not user.is_approved:
            raise serializers.ValidationError("Your account is pending admin approval.")

        data['user'] = user
        return data


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
