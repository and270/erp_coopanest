from django import forms

from registration.models import Anesthesiologist, HospitalClinic, Surgeon
from .models import Procedimento, EscalaAnestesiologista
from datetime import datetime, timedelta

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
            #'telefone_paciente': self.fields['telefone_paciente'],
            'email_paciente': self.fields['email_paciente'],
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
    data_inicio = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/aaaa'}),
        input_formats=['%d/%m/%Y'],
        label="Data de Início"
    )
    data_fim = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/aaaa'}),
        input_formats=['%d/%m/%Y'],
        label="Data de Fim"
    )
    dias_da_semana = forms.MultipleChoiceField(
        choices=EscalaAnestesiologista.DIAS_DA_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = EscalaAnestesiologista
        fields = ['escala_type', 'anestesiologista', 'hora_inicio', 'hora_fim', 'dias_da_semana', 'observacoes']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(EscalaForm, self).__init__(*args, **kwargs)
        if user:
            self.user_group = user.group  # Store the user's group
            self.fields['anestesiologista'].queryset = Anesthesiologist.objects.filter(group=user.group)
        self.fields['hora_inicio'].widget.attrs.update({'class': 'form-control'})
        self.fields['hora_fim'].widget.attrs.update({'class': 'form-control'})
        self.fields['observacoes'].widget.attrs.update({'class': 'form-control'})
        self.fields['dias_da_semana'].widget.attrs.pop('class', None)

    def clean_dias_da_semana(self):
        return self.cleaned_data.get('dias_da_semana', [])
    
    def save(self, commit=True):
        data_inicio = self.cleaned_data['data_inicio']
        data_fim = self.cleaned_data['data_fim']
        dias_da_semana = self.cleaned_data['dias_da_semana']
        hora_inicio = self.cleaned_data['hora_inicio']
        hora_fim = self.cleaned_data['hora_fim']
        observacoes = self.cleaned_data['observacoes']
        escala_type = self.cleaned_data['escala_type']
        anestesiologista = self.cleaned_data['anestesiologista']
        group = self.user_group  # Use the stored user's group

        escalas = []
        current_date = data_inicio
        while current_date <= data_fim:
            # Correctly map Python's weekday to your dias_da_semana keys
            weekday_key = EscalaAnestesiologista.python_weekday_to_dias_da_semana[current_date.weekday()]
            if weekday_key in dias_da_semana:
                escala = EscalaAnestesiologista(
                    escala_type=escala_type,
                    anestesiologista=anestesiologista,
                    data=current_date,
                    hora_inicio=hora_inicio,
                    hora_fim=hora_fim,
                    observacoes=observacoes,
                    group=group  # Set the group
                )
                escalas.append(escala)
            current_date += timedelta(days=1)

        if commit:
            EscalaAnestesiologista.objects.bulk_create(escalas)
        return escalas

class SingleDayEscalaForm(forms.ModelForm):
    class Meta:
        model = EscalaAnestesiologista
        fields = ['escala_type', 'anestesiologista', 'data', 'hora_inicio', 'hora_fim', 'observacoes']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(SingleDayEscalaForm, self).__init__(*args, **kwargs)
        
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

        self.fields['data'].widget = forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
        self.fields['hora_inicio'].widget = forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
        self.fields['hora_fim'].widget = forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
        
        if user:
            self.fields['anestesiologista'].queryset = Anesthesiologist.objects.filter(group=user.group)

