from django import forms
from constants import ANESTESISTA_USER, GESTOR_USER, SECRETARIA_USER
from registration.models import Anesthesiologist, CustomUser, Groups, HospitalClinic, Surgeon
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CustomUserCreationForm(UserCreationForm):
    group = forms.ModelChoiceField(queryset=Groups.objects.all(), required=False, label='Selecione seu Grupo')
    new_group = forms.CharField(required=False, label='Registre o nome do seu Grupo')
    create_new_group = forms.BooleanField(required=False, label='Criar novo grupo')

    class Meta:
        model = CustomUser
        fields = ('email', 'user_type', 'create_new_group', 'group', 'new_group', 'password1', 'password2')
        labels = {
            'email': 'E-mail',
            'user_type': 'Tipo de usuário',
            'password1': 'Senha',
            'password2': 'Confirme a senha',
        }

    def __init__(self, *args, **kwargs):
        super(CustomUserCreationForm, self).__init__(*args, **kwargs)

        user_type_choices = [
            (SECRETARIA_USER, 'Secretária'),
            (GESTOR_USER, 'Gestor'),
            (ANESTESISTA_USER, 'Anestesista')
        ]
        self.fields['user_type'].choices = user_type_choices

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get("user_type")
        create_new_group = cleaned_data.get("create_new_group")
        group = cleaned_data.get("group")
        new_group = cleaned_data.get("new_group")

        if user_type == GESTOR_USER:
            if create_new_group and not new_group:
                raise forms.ValidationError("Por favor, insira o nome do novo grupo.")
            elif not create_new_group and not group:
                raise forms.ValidationError("Por favor, selecione um grupo.")

        elif user_type != GESTOR_USER and not group:
            raise forms.ValidationError("Por favor, selecione um grupo.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user_type = self.cleaned_data.get("user_type")
        create_new_group = self.cleaned_data.get("create_new_group")
        group = self.cleaned_data.get("group")
        new_group = self.cleaned_data.get("new_group")

        if user_type == GESTOR_USER:
            if create_new_group:
                group, created = Groups.objects.get_or_create(name=new_group)
                user.group = group
            else:
                user.group = group
        else:
            user.group = group

        if commit:
            user.save()

        return user

class CustomUserLoginForm(AuthenticationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'password')
        labels = {
            'email': 'E-mail',
            'password': 'Senha',
        }

class AnesthesiologistForm(forms.ModelForm):
    class Meta:
        model = Anesthesiologist
        fields = '__all__'
        labels = {
            'name': 'Nome',
            'date_of_birth': 'Data de Nascimento',
            'cpf': 'CPF',
            'function': 'Função',
            'crm': 'CRM',
            'phone': 'Telefone',
            'email': 'E-mail',
            'role_in_group': 'Cargo no grupo',
            'admission_date': 'Data de Admissão',
            'responsible_hours': 'Horário Responsável',
        }
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'class': 'date-input'}),
            'admission_date': forms.DateInput(attrs={'class': 'date-input'}),
            'cpf': forms.TextInput(attrs={'placeholder': '000.000.000-00'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['user'].queryset = CustomUser.objects.filter(user_type=ANESTESISTA_USER, group=user.group)

        for field in self.fields:
            self.fields[field].initial = None
            if isinstance(self.fields[field], forms.CharField):
                self.fields[field].widget.attrs['placeholder'] = self.fields[field].label

    def clean_user(self):
        user = self.cleaned_data.get('user')
        if user and user.user_type != ANESTESISTA_USER:
            raise ValidationError(_('O usuário selecionado não é um Anestesista.'))
        return user
    
    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].initial = None
            if isinstance(self.fields[field], forms.CharField):
                self.fields[field].widget.attrs['placeholder'] = self.fields[field].label

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].initial = None
            if isinstance(self.fields[field], forms.CharField):
                self.fields[field].widget.attrs['placeholder'] = self.fields[field].label

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user:
            instance.group = user.group  # Set the group to the same as the creating user's group
        if commit:
            instance.save()
        return instance