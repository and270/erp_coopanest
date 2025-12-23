from django.contrib import admin
from django import forms
import re
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.forms import ImportForm, ConfirmImportForm

from agenda.models import EscalaAnestesiologista, Procedimento
from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Membership, Surgeon
from django.contrib.auth.admin import UserAdmin

class CustomImportForm(ImportForm):
    group = forms.ModelChoiceField(queryset=Groups.objects.all(), required=True, label="Grupo de Destino")

class CustomConfirmImportForm(ConfirmImportForm):
    group = forms.ModelChoiceField(queryset=Groups.objects.all(), widget=forms.HiddenInput(), required=False)

class SurgeonResource(resources.ModelResource):
    class Meta:
        model = Surgeon
        fields = ('id', 'name', 'crm', 'specialty', 'phone', 'notes')
        export_order = ('id', 'name', 'crm', 'specialty', 'phone', 'notes')

    def __init__(self, **kwargs):
        # django-import-export may pass extra kwargs depending on version (e.g. file_name)
        super().__init__()
        self.target_group = kwargs.get('group')

    def before_import_row(self, row, **kwargs):
        # Lógica de extração de nome/CRM
        raw_value = row.get('name') or row.get('Nome') or row.get('nome') or row.get('SURGEON') or row.get('Cirurgião')
        
        # If still not found, try to find a cell that looks like "Name (CRM: ...)"
        if not raw_value:
            for key, value in row.items():
                if value and isinstance(value, str) and '(CRM:' in value:
                    raw_value = value
                    break
        
        if raw_value and isinstance(raw_value, str):
            # Regex para capturar: Nome (CRM: XX.XXXXX-X) ou Nome (CRO: XXXXX)
            # Exemplo: DR. AILSON SOARES GOMES (CRM: 52.40783-7)
            match = re.search(r'^(.*?)\s*\((CRM|CRO):\s*(.*?)\)\s*$', raw_value, re.IGNORECASE)
            if match:
                row['name'] = match.group(1).strip()
                row['crm'] = match.group(3).strip()
            else:
                row['name'] = raw_value.strip()

    def get_instance(self, instance_loader, row):
        """
        Evita duplicar cirurgiões quando importar mais de uma vez:
        se já existir um cirurgião no grupo selecionado com mesmo nome/CRM,
        atualiza o existente ao invés de criar um novo.
        """
        if not self.target_group:
            return None

        name = (row.get('name') or '').strip()
        crm = (row.get('crm') or '').strip()
        if not name:
            return None

        qs = Surgeon.objects.filter(group=self.target_group, name__iexact=name)
        if crm:
            qs = qs.filter(crm__iexact=crm)
        return qs.first()

    def before_save_instance(self, instance, *args, **kwargs):
        # Atribui o grupo selecionado no formulário de importação diretamente na instância
        if self.target_group:
            instance.group = self.target_group

@admin.register(Surgeon)
class SurgeonAdmin(ImportExportModelAdmin):
    resource_class = SurgeonResource
    import_form_class = CustomImportForm
    confirm_form_class = CustomConfirmImportForm
    list_display = ('name', 'crm', 'group', 'specialty')
    list_filter = ('group', 'specialty')
    search_fields = ('name', 'crm')

    def get_confirm_form_initial(self, request, import_form):
        initial = super().get_confirm_form_initial(request, import_form)
        if import_form:
            initial['group'] = import_form.cleaned_data['group'].id
        return initial

    def get_import_resource_kwargs(self, request, *args, **kwargs):
        kwargs = super().get_import_resource_kwargs(request, *args, **kwargs)
        # O campo 'group' vem do formulário de importação (POST no upload e no preview)
        group_id = request.POST.get('group')
        if group_id:
            try:
                kwargs.update({"group": Groups.objects.get(id=group_id)})
            except (Groups.DoesNotExist, ValueError):
                pass
        return kwargs

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
# Surgeon registered above via decorator
admin.site.register(HospitalClinic)
admin.site.register(Procedimento)
admin.site.register(EscalaAnestesiologista)
