from django import forms
from constants import ANESTESISTA_USER, GESTOR_USER
from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Surgeon
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CustomUserLoginForm(AuthenticationForm):
    """
    Form for authenticating users against the Coopahub API.
    """
    username = forms.CharField(
        label='Login', 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Digite seu login'})
    )
    password = forms.CharField(
        label='Senha', 
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Digite sua senha'})
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'password')
        labels = {
            'username': 'Login',
            'password': 'Senha',
        }


class AnesthesiologistForm(forms.ModelForm):
    # Add a field for creating a new group
    create_new_group = forms.BooleanField(
        required=False, 
        label='Cadastrar novo grupo?',
        initial=False
    )
    new_group_name = forms.CharField(
        required=False, 
        label='Nome do novo grupo',
        max_length=100
    )
    
    class Meta:
        model = Anesthesiologist
        fields = [
            'name', 'crm', 'date_of_birth', 'cpf', 'phone', 'email', 'role_in_group', 
            'admission_date', 'responsible_hours', 'group', 'create_new_group', 'new_group_name'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'admission_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)  # Pop the user out of kwargs
        super(AnesthesiologistForm, self).__init__(*args, **kwargs)

        if self.user:
            active_role = self.user.get_active_role()
            if active_role == ANESTESISTA_USER:
                # Anesthesiologistas não podem criar/selecionar grupos
                del self.fields['group']
                del self.fields['create_new_group']
                del self.fields['new_group_name']
            elif active_role == GESTOR_USER:
                # Gestores podem selecionar um grupo ou criar um novo
                self.fields['group'].queryset = Groups.objects.all() # Or filter by groups managed by the gestor
                self.fields['group'].required = False

    def clean(self):
        cleaned_data = super().clean()
        create_new_group = cleaned_data.get('create_new_group')
        new_group_name = cleaned_data.get('new_group_name')
        group = cleaned_data.get('group')

        if self.user:
            active_role = self.user.get_active_role()
            if active_role == GESTOR_USER:
                if create_new_group and not new_group_name:
                    self.add_error('new_group_name', 'Nome do grupo é obrigatório se a opção de criar for selecionada.')
                if not create_new_group and not group:
                    self.add_error('group', 'Você deve selecionar um grupo existente ou criar um novo.')
                if create_new_group and group:
                    self.add_error('group', 'Não é possível criar um novo grupo e selecionar um existente ao mesmo tempo.')
        
        return cleaned_data

    def save(self, commit=True):
        instance = super(AnesthesiologistForm, self).save(commit=False)
        
        if self.user:
            active_role = self.user.get_active_role()
            # Lógica para GESTOR
            if active_role == GESTOR_USER:
                create_new_group = self.cleaned_data.get('create_new_group')
                new_group_name = self.cleaned_data.get('new_group_name')
                group = self.cleaned_data.get('group')

                if create_new_group:
                    new_group = Groups.objects.create(name=new_group_name)
                    instance.group = new_group
                else:
                    instance.group = group

            # Lógica para Anestesista (associa ao seu próprio grupo)
            elif active_role == ANESTESISTA_USER:
                instance.group = self.user.group
        
        if commit:
            instance.save()
        return instance


class SurgeonForm(forms.ModelForm):
    class Meta:
        model = Surgeon
        fields = ['name', 'specialty', 'crm', 'phone', 'notes']
        labels = {
            'name': 'Nome',
            'specialty': 'Especialidade',
            'crm': 'CRM',
            'phone': 'Telefone',
            'notes': 'Sugestões de anestesia',
        }
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'phone-mask'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].initial = None

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group
        if commit:
            instance.save()
        return instance

class HospitalClinicForm(forms.ModelForm):
    class Meta:
        model = HospitalClinic
        fields = ['name', 'address', 'surgery_center_phone', 'hospital_phone']
        labels = {
            'name': 'Nome',
            'address': 'Endereço',
            'surgery_center_phone': 'Telefone do Centro Cirúrgico',
            'hospital_phone': 'Telefone do Hospital',
        }
        widgets = {
            'surgery_center_phone': forms.TextInput(attrs={'class': 'phone-mask'}),
            'hospital_phone': forms.TextInput(attrs={'class': 'phone-mask'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['address'].required = False
        self.fields['surgery_center_phone'].required = False
        self.fields['hospital_phone'].required = False
        for field in self.fields:
            self.fields[field].initial = None

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group
        if commit:
            instance.save()
        return instance
    
class AddGroupMembershipForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Groups.objects.all().order_by('name'),
        required=False,
        label='Selecione um grupo existente'
    )
    create_new_group = forms.BooleanField(
        required=False,
        label='Criar novo grupo'
    )
    new_group = forms.CharField(
        required=False,
        label='Nome do novo grupo'
    )
    new_group_email = forms.EmailField(
        required=False,
        label='E-mail do novo grupo'
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # If user is not a Gestor, remove the fields for creating a new group
        active_role = self.user.get_active_role() if self.user else None
        if not self.user or active_role != GESTOR_USER:
            self.fields.pop('create_new_group')
            self.fields.pop('new_group')
            self.fields.pop('new_group_email')

    def clean(self):
        cleaned_data = super().clean()
        # Because for non-gestor, we have already popped the fields out,
        # the code below only applies to a Gestor user.
        create_new_group = cleaned_data.get('create_new_group')
        group = cleaned_data.get('group')
        new_group = cleaned_data.get('new_group')
        new_group_email = cleaned_data.get('new_group_email')

        active_role = self.user.get_active_role() if self.user else None
        if self.user and active_role == GESTOR_USER:
            if create_new_group:
                if not new_group or not new_group_email:
                    raise ValidationError("Por favor, preencha o nome e e-mail do novo grupo.")
            else:
                if not group:
                    raise ValidationError("Por favor, selecione um grupo existente ou crie um novo.")
        else:
            # Non-gestor logic:
            #   - We have removed those fields entirely,
            #     so the only requirement left is that group is selected.
            if not group:
                raise ValidationError("Por favor, selecione um grupo existente.")

        return cleaned_data

    def create_or_get_group(self):
        """Return the group object the user wants to join (or has created).
           For gestor creating a new group, create it. Otherwise, just use `group`.
        """
        create_new_group = self.cleaned_data.get('create_new_group')
        group = self.cleaned_data.get('group')
        new_group = self.cleaned_data.get('new_group')
        new_group_email = self.cleaned_data.get('new_group_email')

        if self.user and self.user.get_active_role() == GESTOR_USER and create_new_group:
            group_obj, created = Groups.objects.get_or_create(
                name=new_group,
                defaults={'email': new_group_email}
            )
            return (group_obj, created)
        else:
            # If not creating new, we didn't actually "create" it, so return (group, False)
            return (group, False)

class GestorAnesthesiologistConfirmForm(forms.Form):
    terms_agreed = forms.BooleanField(
        required=True,
        label="Concordo com os Termos de Serviço"
    )
    privacy_policy_agreed = forms.BooleanField(
        required=True,
        label="Concordo com a Política de Privacidade"
    )
    is_anesthesiologist = forms.BooleanField(
        required=False,
        label="Sou Anestesista"
    )
    name = forms.CharField(
        required=False,
        max_length=255,
        label="Nome Completo",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    crm = forms.CharField(
        required=False,
        max_length=20,
        label="CRM",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        is_anesthesiologist = cleaned_data.get('is_anesthesiologist')
        name = cleaned_data.get('name')
        crm = cleaned_data.get('crm')
        
        if is_anesthesiologist:
            if not name:
                self.add_error('name', 'Este campo é obrigatório quando você é anestesista.')
            if not crm:
                self.add_error('crm', 'Este campo é obrigatório quando você é anestesista.')
        
        return cleaned_data

class TermsAgreementForm(forms.Form):
    terms_agreed = forms.BooleanField(
        required=True,
        label="Concordo com os Termos de Serviço"
    )
    privacy_policy_agreed = forms.BooleanField(
        required=True,
        label="Concordo com a Política de Privacidade"
    )