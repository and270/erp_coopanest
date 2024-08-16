from django import forms
from registration.models import Anesthesiologist, CustomUser, HospitalClinic, Surgeon
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'user_type', 'password1', 'password2')
        labels = {
            'email': 'E-mail',
            'user_type': 'Tipo de usuário',
            'password1': 'Senha',
            'password2': 'Confirme a senha',
        }

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
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].initial = None
            if isinstance(self.fields[field], forms.CharField):
                self.fields[field].widget.attrs['placeholder'] = self.fields[field].label

class SurgeonForm(forms.ModelForm):
    class Meta:
        model = Surgeon
        fields = '__all__'
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

class HospitalClinicForm(forms.ModelForm):
    class Meta:
        model = HospitalClinic
        fields = '__all__'
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