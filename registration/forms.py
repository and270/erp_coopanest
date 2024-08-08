from django import forms
from registration.models import Anesthesiologist, CustomUser, HospitalClinic, Surgeon
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'user_type', 'password1', 'password2')

class CustomUserLoginForm(AuthenticationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'password')

class AnesthesiologistForm(forms.ModelForm):
    class Meta:
        model = Anesthesiologist
        fields = '__all__'

class SurgeonForm(forms.ModelForm):
    class Meta:
        model = Surgeon
        fields = '__all__'

class HospitalClinicForm(forms.ModelForm):
    class Meta:
        model = HospitalClinic
        fields = '__all__'