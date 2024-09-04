from django import forms
from .models import Procedimento, EscalaAnestesiologista

class ProcedimentoForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        exclude = ['group'] 

class EscalaForm(forms.ModelForm):
    class Meta:
        model = EscalaAnestesiologista
        fields = '__all__'
