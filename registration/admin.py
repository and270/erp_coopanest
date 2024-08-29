from django.contrib import admin

from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Surgeon
from django.contrib.auth.admin import UserAdmin

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'user_type', 'group', 'is_staff', 'is_active', 'validado')
    list_filter = ('user_type', 'group', 'is_staff', 'is_active', 'validado')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'user_type', 'group', 'validado')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'user_type', 'group', 'is_staff', 'is_active', 'validado')}
        ),
    )
    search_fields = ('email',)
    ordering = ('email',)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Groups)
admin.site.register(Anesthesiologist)
admin.site.register(Surgeon)
admin.site.register(HospitalClinic)