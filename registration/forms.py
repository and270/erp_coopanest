from django import forms
from registration.models import Anesthesiologist, HospitalClinic, Surgeon

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