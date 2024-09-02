from django import forms
from .models import Procedimento, EscalaAnestesiologista

class ProcedimentoForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        fields = '__all__'

class EscalaForm(forms.ModelForm):
    class Meta:
        model = EscalaAnestesiologista
        fields = '__all__'
