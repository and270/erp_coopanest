from django import forms

from constants import STATUS_FINISHED
from .models import BPS_DESCRIPTIONS, EVA_DESCRIPTIONS, FLACC_DESCRIPTIONS, PAINAD_B_DESCRIPTIONS, AvaliacaoRPA, ProcedimentoQualidade
from financas.models import ProcedimentoFinancas
import pytz

class AvaliacaoRPAForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.EVA_DESCRIPTIONS = EVA_DESCRIPTIONS
        self.FLACC_DESCRIPTIONS = FLACC_DESCRIPTIONS
        self.BPS_DESCRIPTIONS = BPS_DESCRIPTIONS
        self.PAINAD_B_DESCRIPTIONS = PAINAD_B_DESCRIPTIONS

    class Meta:
        model = AvaliacaoRPA
        fields = [
            'tempo_alta_rpa', 'dor_pos_operatoria', 'escala', 'eva_score',
            'evento_adverso', 'evento_adverso_qual', 'ponv',
            'face', 'pernas', 'atividade', 'choro', 'consolabilidade',
            'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador',
            'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad',
            'linguagem_corporal', 'consolabilidade_painad'
        ]
        widgets = {
            'tempo_alta_rpa': forms.TextInput(
                attrs={
                    'type': 'text',
                    'class': 'form-control form-options-text time-input time-mask',
                    'placeholder': 'hh:mm',
                }
            ),
            'dor_pos_operatoria': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'form-options-text'}),
            'escala': forms.RadioSelect(attrs={'class': 'form-options-text'}),
            'eva_score': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 11)], attrs={'class': 'form-options-text'}),
            'evento_adverso': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'form-options-text'}),
            'ponv': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'form-options-text'}),
            'face': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'pernas': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'atividade': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'choro': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'consolabilidade': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'expressao_facial': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'movimentos_membros_superiores': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'adaptacao_ventilador': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'respiracao': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'vocalizacao_negativa': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'expressao_facial_painad': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'linguagem_corporal': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'consolabilidade_painad': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        evento_adverso = cleaned_data.get('evento_adverso')
        evento_adverso_qual = cleaned_data.get('evento_adverso_qual')
        escala = cleaned_data.get('escala')
        dor_pos_operatoria = cleaned_data.get('dor_pos_operatoria')

        # Validate common required fields first
        required_fields = ['tempo_alta_rpa', 'dor_pos_operatoria', 'evento_adverso', 'ponv']
        for field in required_fields:
            if cleaned_data.get(field) is None:
                self.add_error(field, 'Este campo é obrigatório.')

        if evento_adverso is True and not evento_adverso_qual:
            self.add_error('evento_adverso_qual', 'Este campo é obrigatório quando há evento adverso.')

        if not escala:
            self.add_error('escala', 'É necessário selecionar uma escala')

        if escala:
            if escala == 'EVA':
                if cleaned_data.get('eva_score') is None:
                    self.add_error('eva_score', 'Este campo é obrigatório para a escala EVA.')
            elif escala == 'FLACC':
                for field in ['face', 'pernas', 'atividade', 'choro', 'consolabilidade']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala FLACC.')
            elif escala == 'BPS':
                for field in ['expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala BPS.')
            elif escala == 'PAINAD-B':
                for field in ['respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala PAINAD-B.')

        return cleaned_data

class ProcedimentoFinalizacaoForm(forms.ModelForm):
    # Add financial fields
    tipo_cobranca = forms.ChoiceField(
        choices=ProcedimentoFinancas.COBRANCA_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-inline'}),
        required=True
    )
    valor_cobranca = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'data-dependent-on': 'tipo_cobranca',
            'id': 'id_valor_cobranca'
        })
    )
    tipo_pagamento_direto = forms.ChoiceField(
        choices=ProcedimentoFinancas.DIRECT_PAYMENT_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.EVA_DESCRIPTIONS = EVA_DESCRIPTIONS
        self.FLACC_DESCRIPTIONS = FLACC_DESCRIPTIONS
        self.BPS_DESCRIPTIONS = BPS_DESCRIPTIONS
        self.PAINAD_B_DESCRIPTIONS = PAINAD_B_DESCRIPTIONS
        
        # Add custom labels
        self.fields['data_horario_inicio_efetivo'].label = 'Horário de Início'
        self.fields['data_horario_fim_efetivo'].label = 'Horário de Término'
        self.fields['eventos_adversos_graves_desc'].label = 'Qual'
        self.fields['reacao_alergica_grave_desc'].label = 'Qual'
        
        # Modify the widget to include timezone info
        self.fields['data_horario_inicio_efetivo'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['data_horario_fim_efetivo'].input_formats = ['%Y-%m-%dT%H:%M']
        
        if self.instance and self.instance.pk:
            if self.instance.data_horario_inicio_efetivo:
                # Convert to local time for display
                local_tz = pytz.timezone('America/Sao_Paulo')
                local_time = self.instance.data_horario_inicio_efetivo.astimezone(local_tz)
                self.initial['data_horario_inicio_efetivo'] = local_time.strftime('%Y-%m-%dT%H:%M')
            
            if self.instance.data_horario_fim_efetivo:
                # Convert to local time for display
                local_tz = pytz.timezone('America/Sao_Paulo')
                local_time = self.instance.data_horario_fim_efetivo.astimezone(local_tz)
                self.initial['data_horario_fim_efetivo'] = local_time.strftime('%Y-%m-%dT%H:%M')

    class Meta:
        model = ProcedimentoQualidade
        fields = [
            'data_horario_inicio_efetivo', 'data_horario_fim_efetivo',
            'dor_pos_operatoria', 'escala', 'eva_score',
            'face', 'pernas', 'atividade', 'choro', 'consolabilidade',
            'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador',
            'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad',
            'linguagem_corporal', 'consolabilidade_painad',
            'eventos_adversos_graves', 'eventos_adversos_graves_desc',
            'reacao_alergica_grave', 'reacao_alergica_grave_desc',
            'encaminhamento_uti', 'evento_adverso_evitavel',
            'adesao_checklist', 'uso_tecnicas_assepticas',
            'conformidade_diretrizes', 'ponv', 'adesao_profilaxia'
        ]
        widgets = {
            'data_horario_inicio_efetivo': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'data-timezone': 'America/Sao_Paulo'
                }
            ),
            'data_horario_fim_efetivo': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'data-timezone': 'America/Sao_Paulo'
                }
            ),
            'dor_pos_operatoria': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'form-options-text'}),
            'escala': forms.RadioSelect(attrs={'class': 'form-options-text'}),
            'eva_score': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 11)], attrs={'class': 'form-options-text'}),
            'face': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'pernas': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'atividade': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'choro': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'consolabilidade': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 4)], attrs={'class': 'form-options-text'}),
            'expressao_facial': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'movimentos_membros_superiores': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'adaptacao_ventilador': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 5)], attrs={'class': 'form-options-text'}),
            'respiracao': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'vocalizacao_negativa': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'expressao_facial_painad': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'linguagem_corporal': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'consolabilidade_painad': forms.RadioSelect(choices=[(i, str(i)) for i in range(3)], attrs={'class': 'form-options-text'}),
            'eventos_adversos_graves': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'eventos_adversos_graves_desc': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),
            'reacao_alergica_grave': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'reacao_alergica_grave_desc': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
            ),
            'encaminhamento_uti': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'evento_adverso_evitavel': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'adesao_checklist': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'uso_tecnicas_assepticas': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'conformidade_diretrizes': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'ponv': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'adesao_profilaxia': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'tipo_cobranca': forms.RadioSelect(
                attrs={'class': 'form-check-inline'}
            ),
            'tipo_pagamento_direto': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'valor_cobranca': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'data-dependent-on': 'tipo_cobranca',
                    'id': 'id_valor_cobranca'
                }
            ),
        }

    def save(self, commit=True):
        qualidade_instance = super().save(commit=False)
        
        if commit:
            qualidade_instance.save()
            
            # Create or update ProcedimentoFinancas
            financas, _ = ProcedimentoFinancas.objects.get_or_create(
                procedimento=qualidade_instance.procedimento
            )
            financas.tipo_cobranca = self.cleaned_data['tipo_cobranca']
            financas.valor_cobranca = self.cleaned_data['valor_cobranca']
            financas.tipo_pagamento_direto = self.cleaned_data['tipo_pagamento_direto']
            financas.save()
            
            # Update Procedimento status
            procedimento = qualidade_instance.procedimento
            procedimento.status = STATUS_FINISHED
            procedimento.save()

        return qualidade_instance

    def clean(self):
        cleaned_data = super().clean()
        
        inicio = cleaned_data.get('data_horario_inicio_efetivo')
        fim = cleaned_data.get('data_horario_fim_efetivo')
        escala = cleaned_data.get('escala')
        dor_pos_operatoria = cleaned_data.get('dor_pos_operatoria')
        eventos_adversos_graves = cleaned_data.get('eventos_adversos_graves')
        eventos_adversos_graves_desc = cleaned_data.get('eventos_adversos_graves_desc')
        tipo_cobranca = cleaned_data.get('tipo_cobranca')
        tipo_pagamento_direto = cleaned_data.get('tipo_pagamento_direto')

        if inicio:
            # Convert to UTC, then back to Sao Paulo to preserve the exact time
            sp_timezone = pytz.timezone('America/Sao_Paulo')
            inicio = inicio.replace(tzinfo=None)  # Remove any timezone info
            inicio = sp_timezone.localize(inicio)  # Add Sao Paulo timezone
            cleaned_data['data_horario_inicio_efetivo'] = inicio

        if fim:
            # Same treatment for end time
            sp_timezone = pytz.timezone('America/Sao_Paulo')
            fim = fim.replace(tzinfo=None)  # Remove any timezone info
            fim = sp_timezone.localize(fim)  # Add Sao Paulo timezone
            cleaned_data['data_horario_fim_efetivo'] = fim

        # All fields are required
        required_fields = [
            'data_horario_inicio_efetivo', 'data_horario_fim_efetivo', 'dor_pos_operatoria',
            'eventos_adversos_graves', 'reacao_alergica_grave',
            'encaminhamento_uti', 'evento_adverso_evitavel',
            'adesao_checklist', 'uso_tecnicas_assepticas',
            'conformidade_diretrizes', 'ponv', 'adesao_profilaxia',
            'tipo_cobranca'
        ]
        
        for field in required_fields:
            if cleaned_data.get(field) is None:
                self.add_error(field, 'Este campo é obrigatório.')

        if cleaned_data.get('reacao_alergica_grave') and not cleaned_data.get('reacao_alergica_grave_desc'):
            self.add_error('reacao_alergica_grave_desc', 'Este campo é obrigatório quando há reação alérgica grave.')

        if not escala:
            self.add_error('escala', 'É necessário selecionar uma escala')

        if escala:
            if escala == 'EVA':
                if cleaned_data.get('eva_score') is None:
                    self.add_error('eva_score', 'Este campo é obrigatório para a escala EVA.')
            elif escala == 'FLACC':
                for field in ['face', 'pernas', 'atividade', 'choro', 'consolabilidade']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala FLACC.')
            elif escala == 'BPS':
                for field in ['expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala BPS.')
            elif escala == 'PAINAD-B':
                for field in ['respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
                    if cleaned_data.get(field) is None:
                        self.add_error(field, f'Este campo é obrigatório para a escala PAINAD-B.')

        if tipo_cobranca != 'cooperativa' and not cleaned_data.get('valor_cobranca'):
            self.add_error('valor_cobranca', 'Este campo é obrigatório para este tipo de cobrança.')

        if eventos_adversos_graves and not eventos_adversos_graves_desc:
            self.add_error('eventos_adversos_graves_desc', 'Este campo é obrigatório quando há eventos adversos graves.')

        if tipo_cobranca == 'particular' and not tipo_pagamento_direto:
            self.add_error('tipo_pagamento_direto', 'Este campo é obrigatório para pagamento direto.')

        return cleaned_data
