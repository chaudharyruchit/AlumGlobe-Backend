from rest_framework import serializers
from .models import CustomUser, College
from rest_framework_simplejwt.tokens import RefreshToken


class CollegeSerializer(serializers.ModelSerializer):
    class Meta:
        model = College
        fields = ['id', 'name', 'code', 'domain']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    # College code must be numeric (flexible length, only digits)
    college_code = serializers.RegexField(
        regex=r'^\d+$',  # one or more digits
        write_only=True,
        required=True,
        error_messages={
            "invalid": "College code must contain only digits (e.g., 092, 1923, 09712)."
        }
    )
    role = serializers.ChoiceField(
        choices=[('student', 'Student'), ('alumni', 'Alumni'), ('admin', 'Admin')]
    )
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
        college_code = attrs.get("college_code")

        # Roll number required for Student/Alumni
        if role in ["student", "alumni"] and not roll_number:
            raise serializers.ValidationError("Roll number is required for Students and Alumni.")

        # College code required for everyone
        if not college_code:
            raise serializers.ValidationError("College code is required for registration.")

        return attrs

    def validate_college_code(self, value):
        if value:
            try:
                College.objects.get(code=value)
            except College.DoesNotExist:
                raise serializers.ValidationError("Invalid college code.")
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

        # Admin rules
        if user.role == "admin":
            if not college or not college.domain:
                raise serializers.ValidationError("Admin registration requires a valid college with a domain.")
            if not user.email.endswith(f"@{college.domain}"):
                raise serializers.ValidationError(
                    f"Admins must register using official college email (@{college.domain})."
                )
            user.verified = True
            user.is_approved = True   # Auto-approved
            user.is_active = True     # Can login immediately
            user.is_staff = True
            user.is_superuser = True


        # Student / Alumni rules
        elif user.role in ["student", "alumni"]:
            if college and college.domain and user.email.endswith(f"@{college.domain}"):
                user.verified = True
            else:
                user.verified = False
            user.is_approved = False  # Requires admin approval
            user.is_active = False    # Block login until approved

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
            raise serializers.ValidationError("Invalid credentials.")

        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials.")

        # Block login until approved
        if not user.is_active or not user.is_approved:
            raise serializers.ValidationError("Your account is pending admin approval.")

        data['user'] = user
        return data


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
