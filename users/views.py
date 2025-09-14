from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import RegisterSerializer, LoginSerializer, get_tokens_for_user
from .models import CustomUser, College
from rest_framework_simplejwt.tokens import RefreshToken

# Social verification imports
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import requests as http_requests
import os

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")


# ---------------- Register ----------------
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Response message based on approval
            if user.is_approved:
                tokens = get_tokens_for_user(user)
                return Response({
                    "message": "Registration successful. You can log in now.",
                    "user_id": user.id,
                    "tokens": tokens
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    "message": "Registration successful. Please wait for admin approval before logging in.",
                    "user_id": user.id
                }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------- Login ----------------
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Prevent login if not approved
            if not user.is_approved:
                return Response({"detail": "Your account is pending admin approval."}, status=status.HTTP_403_FORBIDDEN)

            tokens = get_tokens_for_user(user)
            return Response({
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "college": user.college.code if user.college else None,
                    "roll_number": getattr(user, "roll_number", None)
                },
                "tokens": tokens
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------- Google Auth ----------------
class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('id_token')
        role = request.data.get('role')
        college_code = request.data.get('college_code', None)
        roll_number = request.data.get('roll_number', None)

        if not token:
            return Response({"detail": "No id_token provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
            google_sub = idinfo.get('sub')
            email = idinfo.get('email')
            name = idinfo.get('name') or email.split('@')[0]

            # find existing user
            user = None
            try:
                user = CustomUser.objects.get(google_sub=google_sub)
            except CustomUser.DoesNotExist:
                try:
                    user = CustomUser.objects.get(email=email)
                except CustomUser.DoesNotExist:
                    pass

            if user is None:
                username = email.split('@')[0]
                user = CustomUser(username=username, email=email, role=role)
                user.google_sub = google_sub
                user.first_name = name

                if college_code:
                    try:
                        user.college = College.objects.get(code=college_code)
                        if user.college.domain and email.endswith(user.college.domain):
                            user.verified = True
                    except College.DoesNotExist:
                        pass

                if role in ["student", "alumni"]:
                    user.roll_number = roll_number
                    user.is_approved = False
                    user.is_active = False
                elif role == "admin":
                    if not user.college or not user.college.domain or not email.endswith(f"@{user.college.domain}"):
                        return Response({"detail": "Admins must register with official college email."}, status=status.HTTP_400_BAD_REQUEST)
                    user.verified = True
                    user.is_approved = True

                user.set_unusable_password()
                user.save()
            else:
                if not user.google_sub:
                    user.google_sub = google_sub
                    user.save()

            if not user.is_approved:
                return Response({"message": "Account created. Please wait for admin approval."})

            tokens = get_tokens_for_user(user)
            return Response({"user": {"id": user.id, "email": user.email, "role": user.role}, "tokens": tokens})

        except ValueError as e:
            return Response({"detail": "Invalid token", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------- LinkedIn Auth ----------------
class LinkedInAuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        access_token = request.data.get('access_token')
        role = request.data.get('role')
        college_code = request.data.get('college_code', None)
        roll_number = request.data.get('roll_number', None)

        if not access_token:
            return Response({"detail": "No access_token provided"}, status=status.HTTP_400_BAD_REQUEST)

        headers = {"Authorization": f"Bearer {access_token}"}
        profile_url = "https://api.linkedin.com/v2/me"
        email_url = "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))"

        try:
            p_resp = http_requests.get(profile_url, headers=headers)
            e_resp = http_requests.get(email_url, headers=headers)
            if p_resp.status_code != 200:
                return Response({"detail": "LinkedIn profile fetch failed", "status": p_resp.status_code, "text": p_resp.text}, status=status.HTTP_400_BAD_REQUEST)

            p_json = p_resp.json()
            e_json = e_resp.json()
            linkedin_id = p_json.get('id')
            firstName = p_json.get('localizedFirstName')
            lastName = p_json.get('localizedLastName')
            email = None
            try:
                email = e_json['elements'][0]['handle~']['emailAddress']
            except:
                pass

            user = None
            if linkedin_id:
                try:
                    user = CustomUser.objects.get(linkedin_id=linkedin_id)
                except CustomUser.DoesNotExist:
                    pass
            if user is None and email:
                try:
                    user = CustomUser.objects.get(email=email)
                except CustomUser.DoesNotExist:
                    pass

            if user is None:
                username = (email.split('@')[0] if email else f"li_{linkedin_id}")
                user = CustomUser(username=username, email=email, role=role)
                user.linkedin_id = linkedin_id
                user.first_name = firstName
                user.last_name = lastName

                if college_code:
                    try:
                        user.college = College.objects.get(code=college_code)
                        if user.college.domain and email and email.endswith(user.college.domain):
                            user.verified = True
                    except College.DoesNotExist:
                        pass

                if role in ["student", "alumni"]:
                    user.roll_number = roll_number
                    user.is_approved = False
                    user.is_active = False
                elif role == "admin":
                    if not user.college or not user.college.domain or not email.endswith(f"@{user.college.domain}"):
                        return Response({"detail": "Admins must register with official college email."}, status=status.HTTP_400_BAD_REQUEST)
                    user.verified = True
                    user.is_approved = True

                user.set_unusable_password()
                user.save()
            else:
                if not user.linkedin_id:
                    user.linkedin_id = linkedin_id
                    user.save()

            if not user.is_approved:
                return Response({"message": "Account created. Please wait for admin approval."})

            tokens = get_tokens_for_user(user)
            return Response({"user": {"id": user.id, "email": user.email, "role": user.role}, "tokens": tokens})

        except Exception as e:
            return Response({"detail": "LinkedIn error", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
