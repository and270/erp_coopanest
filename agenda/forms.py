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
        label="Previsão de Término"
    )

    cpf_paciente = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="CPF do Paciente",
        required=False
    )

    anestesistas_responsaveis = forms.ModelMultipleChoiceField(
        queryset=Anesthesiologist.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
        required=False,
        label="Anestesistas Responsáveis"
    )

    class Meta:
        model = Procedimento
        exclude = ['group', 'data_horario', 'data_horario_fim', 'nps_token', 'csat_score', 'clareza_informacoes', 'comunicacao_disponibilidade', 'conforto_seguranca', 'comentario_adicional']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)

        super(ProcedimentoForm, self).__init__(*args, **kwargs)

        self.fields['procedimento_type'].label = 'Tipo de Procedimento'
        self.fields['data'].label = 'Data do Procedimento'
        self.fields['time'].label = 'Hora do Procedimento'

        self.fields = {
            'procedimento_type': self.fields['procedimento_type'],
            'data': self.fields['data'],
            'time': self.fields['time'],
            'end_time': self.fields['end_time'],
            'nome_paciente': self.fields['nome_paciente'],
            'email_paciente': self.fields['email_paciente'],
            'convenio': self.fields['convenio'],
            'procedimento': self.fields['procedimento'],
            'hospital': self.fields['hospital'],
            'outro_local': self.fields['outro_local'],
            'cirurgiao': self.fields['cirurgiao'],
            'anestesistas_responsaveis': self.fields['anestesistas_responsaveis'],
            'visita_pre_anestesica': self.fields['visita_pre_anestesica'],
            'data_visita_pre_anestesica': self.fields['data_visita_pre_anestesica'],
            'foto_anexo': self.fields['foto_anexo'],
            'nome_responsavel_visita': self.fields['nome_responsavel_visita'],
            'cpf_paciente': self.fields['cpf_paciente'],
        }

        if user:
            # Filter and order all ForeignKey fields by name
            self.fields['cirurgiao'].queryset = Surgeon.objects.filter(group=user.group).order_by('name')
            self.fields['hospital'].queryset = HospitalClinic.objects.filter(group=user.group).order_by('name')
            self.fields['anestesistas_responsaveis'].queryset = Anesthesiologist.objects.filter(group=user.group).order_by('name')

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
    
class SurveyForm(forms.ModelForm):
    class Meta:
        model = Procedimento
        fields = ['satisfacao_geral', 'clareza_informacoes', 'comunicacao_disponibilidade', 'conforto_seguranca', 'comentario_adicional']
        widgets = {
            'satisfacao_geral': forms.RadioSelect(attrs={'class': 'satisfaction-radio'}),
            'clareza_informacoes': forms.RadioSelect(attrs={'class': 'satisfaction-radio'}),
            'comunicacao_disponibilidade': forms.RadioSelect(attrs={'class': 'satisfaction-radio'}),
            'conforto_seguranca': forms.RadioSelect(attrs={'class': 'satisfaction-radio'}),
            'comentario_adicional': forms.Textarea(attrs={'class': 'form-control'}),
        }
        labels = {
            'satisfacao_geral': 'Em uma escala de 1 a 5, quão satisfeito você está com o serviço de anestesia que recebeu?',
            'clareza_informacoes': 'Clareza das informações fornecidas pelo anestesista',
            'comunicacao_disponibilidade': 'Comunicação e disponibilidade do anestesista',
            'conforto_seguranca': 'Conforto e segurança durante o procedimento',
            'comentario_adicional': 'Você gostaria de deixar algum comentário adicional sobre sua experiência?'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ['satisfacao_geral', 'clareza_informacoes', 'comunicacao_disponibilidade', 'conforto_seguranca']:
            self.fields[field_name].empty_label = None
            self.fields[field_name].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Calculate CSAT score
        total_responses = 4
        satisfied_responses = sum(
            1 for score in [
                self.cleaned_data['satisfacao_geral'],
                self.cleaned_data['clareza_informacoes'],
                self.cleaned_data['comunicacao_disponibilidade'],
                self.cleaned_data['conforto_seguranca']
            ] if score in [4, 5]  # Count 'Satisfeito' and 'Muito Satisfeito'
        )
        
        instance.csat_score = (satisfied_responses / total_responses) * 100
        
        if commit:
            instance.save()
        return instance

class EscalaForm(forms.ModelForm):
    TODOS_OS_DIAS = 'todos'
    
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
        choices=[(TODOS_OS_DIAS, 'Todos os Dias')] + list(EscalaAnestesiologista.DIAS_DA_SEMANA),
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
        dias = self.cleaned_data.get('dias_da_semana', [])
        if self.TODOS_OS_DIAS in dias:
            return [day[0] for day in EscalaAnestesiologista.DIAS_DA_SEMANA]
        return dias
    
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
