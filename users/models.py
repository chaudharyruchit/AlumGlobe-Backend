from django.db import models
from django.contrib.auth.models import AbstractUser

ROLE_CHOICES = (
    ('student', 'Student'),
    ('alumni', 'Alumni'),
    ('admin', 'Admin'),
)


class College(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True)  # college_code for multi-tenant
    domain = models.CharField(max_length=255, blank=True, null=True)  # official email domain

    def __str__(self):
        return f"{self.name} ({self.code})"


class CustomUser(AbstractUser):
    # inherited fields: username, first_name, last_name, password, is_active
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    college = models.ForeignKey(College, on_delete=models.SET_NULL, null=True, blank=True)

    roll_number = models.CharField(max_length=50, blank=True, null=True)  # required for student/alumni
    linkedin_url = models.URLField(blank=True, null=True)

    # OAuth identifiers
    google_sub = models.CharField(max_length=255, blank=True, null=True)   # Google subject (sub)
    linkedin_id = models.CharField(max_length=255, blank=True, null=True)

    # verification / approval
    verified = models.BooleanField(default=False)   # admin verified or auto-verified via domain
    is_approved = models.BooleanField(default=False)  # only after admin approval for students/alumni

    REQUIRED_FIELDS = ['email']

    def save(self, *args, **kwargs):
        # Admins must use official college domain (if provided)
        if self.role == "admin" and self.college and self.college.domain:
            if not self.email.endswith(f"@{self.college.domain}"):
                raise ValueError(f"Admins must use the official email domain: @{self.college.domain}")
            self.is_approved = True   # auto-approved admins

        # Students and Alumni → must wait for approval
        if self.role in ["student", "alumni"] and not self.pk:
            self.is_active = False   # prevent login until approved

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role}) - {self.college.name if self.college else 'No College'}"

