from django import forms
from .models import Procedimento, EscalaAnestesiologista
from datetime import datetime

class ProcedimentoForm(forms.ModelForm):

    data = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/aaaa'}),
        input_formats=['%d/%m/%Y'],
        label="Data do Procedimento"
    )
    time = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'hh:mm'}),
        input_formats=['%H:%M'],
        label="Hora do Procedimento"
    )

    class Meta:
        model = Procedimento
        exclude = ['group', 'data_horario'] 

    def save(self, commit=True):
        # Combine the date and time fields to form the `data_horario`
        instance = super().save(commit=False)
        date = self.cleaned_data['data']
        time = self.cleaned_data['time']
        instance.data_horario = datetime.combine(date, time)
        if commit:
            instance.save()
        return instance

class EscalaForm(forms.ModelForm):
    class Meta:
        model = EscalaAnestesiologista
        fields = '__all__'
