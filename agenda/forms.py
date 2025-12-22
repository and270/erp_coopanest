from django import forms

from qualidade.models import ProcedimentoQualidade
from registration.models import Anesthesiologist, HospitalClinic, Surgeon
from .models import Procedimento, EscalaAnestesiologista, ProcedimentoDetalhes, Convenios
from financas.models import ProcedimentoFinancas
from datetime import datetime, timedelta
from dal import autocomplete
from dal_select2 import widgets as dal_widgets
from constants import CONSULTA_PROCEDIMENTO, CIRURGIA_AMBULATORIAL_PROCEDIMENTO

class ProcedimentoForm(forms.ModelForm):

    procedimento_principal = forms.ModelChoiceField(
        queryset=ProcedimentoDetalhes.objects.all(),
        widget=dal_widgets.ModelSelect2(
            url='procedure-autocomplete',
            attrs={
                'data-placeholder': 'Digite para buscar...',
                'data-minimum-input-length': 2,
            }
        ),
        label='Procedimento Principal',
    )

    convenio = forms.ModelChoiceField(
        queryset=Convenios.objects.all(),
        widget=dal_widgets.ModelSelect2(
            url='convenio-autocomplete',
            attrs={
                'data-placeholder': 'Digite para buscar convênio...',
                'data-minimum-input-length': 2,
            }
        ),
        label='Convênio (selecione ou crie abaixo)',
        required=False,
    )

    convenio_nome_novo = forms.CharField(
        label='Ou, Nome do Novo Convênio',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Digite se não encontrar na lista acima'})
    )

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
        label="Previsão de Término",
        required=False
    )

    cpf_paciente = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="CPF do Paciente",
        required=False
    )

    cooperado = forms.ModelChoiceField(
        queryset=Anesthesiologist.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        label='Cooperado'
    )
    anestesistas_livres = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label='Anestesistas (livre)'
    )

    # Financial fields
    tipo_cobranca = forms.ChoiceField(
        choices=[('', '--- Selecione ---')] + ProcedimentoFinancas.COBRANCA_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-inline'}),
        required=False,
        label='Tipo de Cobrança'
    )
    valor_faturado = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_valor_faturado'
        }),
        label='Valor Faturado'
    )
    tipo_pagamento_direto = forms.ChoiceField(
        choices=ProcedimentoFinancas.DIRECT_PAYMENT_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Forma de Pagamento (Direto)'
    )
    data_pagamento = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'dd/mm/aaaa'}),
        required=False,
        label='Data do Pagamento (Hospital/Direto)'
    )

    def clean_valor_faturado(self):
        valor = self.cleaned_data.get('valor_faturado')
        # DecimalField might already have parsed it if JS worked
        # If JS failed, it might be a string or None
        if not valor:
            # Check raw data if cleaned_data is empty
            raw_valor = self.data.get('valor_faturado')
            if raw_valor and isinstance(raw_valor, str):
                cleaned_valor = raw_valor.replace('R$', '').replace('.', '').replace(',', '.').replace(' ', '').strip()
                try:
                    return cleaned_valor
                except (ValueError, TypeError):
                    return None
        return valor

    class Meta:
        model = Procedimento
        fields = [
            'nome_paciente', 'email_paciente', 'cpf_paciente',
            'convenio', 'convenio_nome_novo', 'procedimento_principal', 'hospital', 'outro_local',
            'cirurgiao', 'cirurgiao_nome',
            'cooperado',
            'anestesistas_livres',
            'visita_pre_anestesica',
            'data_visita_pre_anestesica', 'foto_anexo', 'nome_responsavel_visita',
            'tipo_procedimento', # Added new field
            'tipo_clinica', # New clinic type field (optional)
            'tipo_cobranca', 'valor_faturado', 'tipo_pagamento_direto', 'data_pagamento'
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(ProcedimentoForm, self).__init__(*args, **kwargs)
        self.user_group = None

        if user:
            self.user_group = user.group
            anesthesiologist_qs = Anesthesiologist.objects.filter(group=user.group).order_by('name')
            self.fields['cirurgiao'].queryset = Surgeon.objects.filter(group=user.group).order_by('name')
            self.fields['hospital'].queryset = HospitalClinic.objects.filter(group=user.group).order_by('name')
            self.fields['cooperado'].queryset = anesthesiologist_qs
            self.fields['convenio'].queryset = Convenios.objects.all().order_by('name')
            self.fields['procedimento_principal'].queryset = ProcedimentoDetalhes.objects.all().order_by('name')

        self.fields['data_visita_pre_anestesica'].widget.attrs.update({'class': 'form-control conditional-field'})
        self.fields['foto_anexo'].widget.attrs.update({'class': 'form-control conditional-field'})
        self.fields['nome_responsavel_visita'].widget.attrs.update({'class': 'form-control conditional-field'})
        self.fields['cirurgiao_nome'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Digite o nome do cirurgião não cadastrado'
        })
        # Add placeholder to cooperado selector
        self.fields['cooperado'].empty_label = "--- Selecione ---"
        # Hide the label for the original field in the template using JS/CSS might be better
        # self.fields['anestesistas_responsaveis'].label = ''
        self.fields['tipo_procedimento'].widget.attrs.update({'class': 'form-control'})
        self.fields['tipo_procedimento'].empty_label = "--- Selecione o Tipo ---"
        # Style for optional clinic type selector
        if 'tipo_clinica' in self.fields:
            field = self.fields['tipo_clinica']
            field.widget.attrs.update({'class': 'form-control'})
            # Sort clinic type options alphabetically while preserving blank choices on top
            choices = list(field.choices)
            empty_choices = []
            clinic_choices = []
            for value, label in choices:
                if value in (None, ''):
                    empty_choices.append((value, label))
                else:
                    clinic_choices.append((value, label))
            clinic_choices.sort(key=lambda choice: choice[1])
            field.choices = empty_choices + clinic_choices

        # Pre-fill financial fields if editing
        if self.instance and self.instance.pk:
            try:
                financas = ProcedimentoFinancas.objects.get(procedimento=self.instance)
                self.initial['tipo_cobranca'] = financas.tipo_cobranca
                self.initial['valor_faturado'] = financas.valor_faturado
                self.initial['tipo_pagamento_direto'] = financas.tipo_pagamento_direto
                self.initial['data_pagamento'] = financas.data_pagamento
            except ProcedimentoFinancas.DoesNotExist:
                pass


    def save(self, commit=True):
        instance = super().save(commit=False)
        date = self.cleaned_data['data']
        time = self.cleaned_data['time']
        end_time = self.cleaned_data.get('end_time')
        instance.data_horario = datetime.combine(date, time)
        instance.data_horario_fim = datetime.combine(date, end_time) if end_time else None

        # Auto-classify procedure type
        procedimento_principal = self.cleaned_data.get('procedimento_principal')
        if procedimento_principal and procedimento_principal.codigo_procedimento == '10101012':
            instance.procedimento_type = CONSULTA_PROCEDIMENTO
        else:
            instance.procedimento_type = CIRURGIA_AMBULATORIAL_PROCEDIMENTO

        convenio_nome_novo = self.cleaned_data.get('convenio_nome_novo')
        convenio_selecionado = self.cleaned_data.get('convenio')

        if convenio_nome_novo:
            convenio_obj, created = Convenios.objects.get_or_create(name=convenio_nome_novo.strip())
            instance.convenio = convenio_obj
        elif convenio_selecionado:
            instance.convenio = convenio_selecionado
        # If neither is provided, instance.convenio remains what it was (or None if new)
        # as 'convenio' field is not required.

        if commit:
            if self.user_group:
                instance.group = self.user_group
            instance.save()
            self.save_m2m()

            # Handle financial record
            tipo_cobranca = self.cleaned_data.get('tipo_cobranca')
            if tipo_cobranca:
                try:
                    financas = ProcedimentoFinancas.objects.get(procedimento=instance)
                except ProcedimentoFinancas.DoesNotExist:
                    financas = ProcedimentoFinancas(procedimento=instance, group=instance.group)

                financas.tipo_cobranca = tipo_cobranca
                if financas.tipo_cobranca == 'cortesia':
                    financas.valor_faturado = 0
                    financas.valor_recebido = 0
                    financas.valor_recuperado = 0
                else:
                    financas.valor_faturado = self.cleaned_data.get('valor_faturado')

                financas.tipo_pagamento_direto = self.cleaned_data.get('tipo_pagamento_direto') if financas.tipo_cobranca == 'particular' else None
                data_pagamento = self.cleaned_data.get('data_pagamento')
                financas.data_pagamento = data_pagamento

                if data_pagamento:
                    financas.status_pagamento = 'processo_finalizado'
                    financas.valor_recebido = financas.valor_faturado
                elif not financas.status_pagamento or financas.status_pagamento == 'em_processamento':
                    financas.status_pagamento = 'em_processamento'

                financas.save()

        return instance

class SurveyForm(forms.ModelForm):
    class Meta:
        model = ProcedimentoQualidade
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
