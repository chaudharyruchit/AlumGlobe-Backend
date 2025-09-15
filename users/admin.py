from django.contrib import admin
from .models import CustomUser, College

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'college', 'is_approved')
    list_filter = ('role', 'college', 'is_approved')
    search_fields = ('username', 'email')
    actions = ['approve_users']

    # Bulk approve action
    def approve_users(self, request, queryset):
        queryset.update(is_approved=True, is_active=True)
    approve_users.short_description = "Approve selected users"

    # College admin only sees their college users
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin' and request.user.college:
            return qs.filter(college=request.user.college)
        return qs
@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'domain')
    search_fields = ('name', 'code')

# Register your models here.
