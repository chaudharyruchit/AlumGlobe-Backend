from django.urls import path
from .views import RegisterView, LoginView, GoogleAuthView, LinkedInAuthView

# ✅ urlpatterns must be a list
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('social/google/', GoogleAuthView.as_view(), name='google-auth'),
    path('social/linkedin/', LinkedInAuthView.as_view(), name='linkedin-auth'),
]
