from django.contrib import admin

from agenda.models import EscalaAnestesiologista, Procedimento
from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Membership, Surgeon
from django.contrib.auth.admin import UserAdmin

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'group', 'is_staff', 'is_active', 'validado')
    list_filter = ('group', 'is_staff', 'is_active', 'validado')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'group', 'validado')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'group', 'is_staff', 'is_active', 'validado')}
        ),
    )
    search_fields = ('email',)
    ordering = ('email',)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Membership)
admin.site.register(Groups)
admin.site.register(Anesthesiologist)
admin.site.register(Surgeon)
admin.site.register(HospitalClinic)
admin.site.register(Procedimento)
admin.site.register(EscalaAnestesiologista)