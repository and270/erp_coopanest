from django import forms

from registration.models import Anesthesiologist, HospitalClinic, Surgeon
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

    end_time = forms.TimeField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'hh:mm'}),
        input_formats=['%H:%M'],
        label="Hora de Término"
    )

    class Meta:
        model = Procedimento
        exclude = ['group', 'data_horario', 'data_horario_fim']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)

        super(ProcedimentoForm, self).__init__(*args, **kwargs)
        # Reorder fields: set the order manually
        self.fields['procedimento_type'].label = 'Tipo de Procedimento'
        self.fields['data'].label = 'Data do Procedimento'
        self.fields['time'].label = 'Hora do Procedimento'

        # Set the order explicitly: first procedimento_type, then data and time
        self.fields = {
            'procedimento_type': self.fields['procedimento_type'],
            'data': self.fields['data'],
            'time': self.fields['time'],
            'end_time': self.fields['end_time'],
            'nome_paciente': self.fields['nome_paciente'],
            'contato_pacinete': self.fields['contato_pacinete'],
            'procedimento': self.fields['procedimento'],
            'hospital': self.fields['hospital'],
            'outro_local': self.fields['outro_local'],
            'cirurgiao': self.fields['cirurgiao'],
            'anestesista_responsavel': self.fields['anestesista_responsavel'],
            'link_nps': self.fields['link_nps'],
            'visita_pre_anestesica': self.fields['visita_pre_anestesica'],
            'data_visita_pre_anestesica': self.fields['data_visita_pre_anestesica'],
            'foto_anexo': self.fields['foto_anexo'],
            'nome_responsavel_visita': self.fields['nome_responsavel_visita']
        }

        if user:
            # Filter the ForeignKey fields by the user's group
            self.fields['anestesista_responsavel'].queryset = Anesthesiologist.objects.filter(group=user.group)
            self.fields['cirurgiao'].queryset = Surgeon.objects.filter(group=user.group)
            self.fields['hospital'].queryset = HospitalClinic.objects.filter(group=user.group)

        # Add CSS classes to the conditional fields
        self.fields['data_visita_pre_anestesica'].widget.attrs.update({'class': 'form-control conditional-field'})
        self.fields['foto_anexo'].widget.attrs.update({'class': 'form-control conditional-field'})
        self.fields['nome_responsavel_visita'].widget.attrs.update({'class': 'form-control conditional-field'})

    def save(self, commit=True):
        # Combine the date and time fields to form the `data_horario`
        instance = super().save(commit=False)
        date = self.cleaned_data['data']
        time = self.cleaned_data['time']
        end_time = self.cleaned_data['end_time']
        instance.data_horario = datetime.combine(date, time)
        instance.data_horario_fim = datetime.combine(date, end_time)
        if commit:
            instance.save()
        return instance

class EscalaForm(forms.ModelForm):
    class Meta:
        model = EscalaAnestesiologista
        fields = '__all__'
