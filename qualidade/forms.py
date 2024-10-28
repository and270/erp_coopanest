from django import forms
from .models import AvaliacaoRPA
from agenda.models import Procedimento

class AvaliacaoRPAForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.EVA_DESCRIPTIONS = AvaliacaoRPA.EVA_DESCRIPTIONS
        self.FLACC_DESCRIPTIONS = AvaliacaoRPA.FLACC_DESCRIPTIONS
        self.BPS_DESCRIPTIONS = AvaliacaoRPA.BPS_DESCRIPTIONS
        self.PAINAD_B_DESCRIPTIONS = AvaliacaoRPA.PAINAD_B_DESCRIPTIONS

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
            'tempo_alta_rpa': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-options-text'}),
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add custom labels
        self.fields['data_horario_inicio_efetivo'].label = 'Horário de Início'
        self.fields['data_horario_fim_efetivo'].label = 'Horário de Término'
        self.fields['eventos_adversos_graves_desc'].label = 'Qual'
        self.fields['reacao_alergica_grave_desc'].label = 'Qual'
        
        # Preenche os campos datetime se o objeto já existir
        if self.instance and self.instance.pk:  # verifica se é um objeto existente
            if self.instance.data_horario_inicio_efetivo:
                # Converte para o formato aceito pelo input datetime-local
                self.initial['data_horario_inicio_efetivo'] = self.instance.data_horario_inicio_efetivo.strftime('%Y-%m-%dT%H:%M')
            if self.instance.data_horario_fim_efetivo:
                self.initial['data_horario_fim_efetivo'] = self.instance.data_horario_fim_efetivo.strftime('%Y-%m-%dT%H:%M')

    class Meta:
        model = Procedimento
        fields = [
            'data_horario_inicio_efetivo',
            'data_horario_fim_efetivo',
            'dor_pos_operatoria_imediata',
            'eventos_adversos_graves',
            'eventos_adversos_graves_desc',
            'reacao_alergica_grave',
            'reacao_alergica_grave_desc',
            'encaminhamento_uti',
            'evento_adverso_evitavel',
            'adesao_checklist',
            'uso_tecnicas_assepticas',
            'conformidade_diretrizes',
            'ponv',
            'adesao_profilaxia',
            'tipo_cobranca',
            'valor_cobranca',
        ]
        widgets = {
            'data_horario_inicio_efetivo': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            ),
            'data_horario_fim_efetivo': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            ),
            'dor_pos_operatoria_imediata': forms.RadioSelect(
                choices=[(i, str(i)) for i in range(1, 11)], 
                attrs={'class': 'form-options-text'}
            ),
            'eventos_adversos_graves': forms.RadioSelect(
                choices=[(True, 'Sim'), (False, 'Não')],
                attrs={'class': 'form-check-inline'}
            ),
            'eventos_adversos_graves_desc': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
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
            'valor_cobranca': forms.NumberInput(
                attrs={'class': 'form-control'}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        
        # All fields are required
        required_fields = [
            'data_horario_inicio_efetivo', 'data_horario_fim_efetivo', 'dor_pos_operatoria_imediata',
            'eventos_adversos_graves', 'reacao_alergica_grave',
            'encaminhamento_uti', 'evento_adverso_evitavel',
            'adesao_checklist', 'uso_tecnicas_assepticas',
            'conformidade_diretrizes', 'ponv', 'adesao_profilaxia',
            'tipo_cobranca', 'valor_cobranca'
        ]
        
        for field in required_fields:
            if cleaned_data.get(field) is None:
                self.add_error(field, 'Este campo é obrigatório.')

        # Check description fields when related fields are True
        if cleaned_data.get('eventos_adversos_graves') and not cleaned_data.get('eventos_adversos_graves_desc'):
            self.add_error('eventos_adversos_graves_desc', 'Este campo é obrigatório quando há eventos adversos graves.')

        if cleaned_data.get('reacao_alergica_grave') and not cleaned_data.get('reacao_alergica_grave_desc'):
            self.add_error('reacao_alergica_grave_desc', 'Este campo é obrigatório quando há reação alérgica grave.')

        return cleaned_data
