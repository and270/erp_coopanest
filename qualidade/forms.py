from django import forms
from .models import AvaliacaoRPA

class AvaliacaoRPAForm(forms.ModelForm):
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
            'tempo_alta_rpa': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control fomr-options-text'}),
            'dor_pos_operatoria': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'fomr-options-text'}),
            'escala': forms.RadioSelect(attrs={'class': 'fomr-options-text'}),
            'eva_score': forms.NumberInput(attrs={'min': 1, 'max': 10, 'class': 'form-control fomr-options-text'}),
            'evento_adverso': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'fomr-options-text'}),
            'ponv': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')], attrs={'class': 'fomr-options-text'}),
            'face': forms.NumberInput(attrs={'min': 1, 'max': 3, 'class': 'form-control fomr-options-text'}),
            'pernas': forms.NumberInput(attrs={'min': 1, 'max': 3, 'class': 'form-control fomr-options-text'}),
            'atividade': forms.NumberInput(attrs={'min': 1, 'max': 3, 'class': 'form-control fomr-options-text'}),
            'choro': forms.NumberInput(attrs={'min': 1, 'max': 3, 'class': 'form-control fomr-options-text'}),
            'consolabilidade': forms.NumberInput(attrs={'min': 1, 'max': 3, 'class': 'form-control fomr-options-text'}),
            'expressao_facial': forms.NumberInput(attrs={'min': 1, 'max': 4, 'class': 'form-control fomr-options-text'}),
            'movimentos_membros_superiores': forms.NumberInput(attrs={'min': 1, 'max': 4, 'class': 'form-control fomr-options-text'}),
            'adaptacao_ventilador': forms.NumberInput(attrs={'min': 1, 'max': 4, 'class': 'form-control fomr-options-text'}),
            'respiracao': forms.NumberInput(attrs={'min': 0, 'max': 2, 'class': 'form-control fomr-options-text'}),
            'vocalizacao_negativa': forms.NumberInput(attrs={'min': 0, 'max': 2, 'class': 'form-control fomr-options-text'}),
            'expressao_facial_painad': forms.NumberInput(attrs={'min': 0, 'max': 2, 'class': 'form-control fomr-options-text'}),
            'linguagem_corporal': forms.NumberInput(attrs={'min': 0, 'max': 2, 'class': 'form-control fomr-options-text'}),
            'consolabilidade_painad': forms.NumberInput(attrs={'min': 0, 'max': 2, 'class': 'form-control fomr-options-text'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['evento_adverso_qual'].widget.attrs.update({
            'rows': 3,
            'class': 'form-control fomr-options-text'
        })

    def clean(self):
        cleaned_data = super().clean()
        escala = cleaned_data.get('escala')

        if escala == 'EVA':
            # Validate EVA specific fields
            if cleaned_data.get('') is None:
                self.add_error('eva_score', 'Este campo é obrigatório para a escala EVA.')
        elif escala == 'FLACC':
            # Validate FLACC specific fields
            for field in ['face', 'pernas', 'atividade', 'choro', 'consolabilidade']:
                if cleaned_data.get(field) is None:
                    self.add_error(field, f'Este campo é obrigatório para a escala FLACC.')
        elif escala == 'BPS':
            # Validate BPS specific fields
            for field in ['expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador']:
                if cleaned_data.get(field) is None:
                    self.add_error(field, f'Este campo é obrigatório para a escala BPS.')
        elif escala == 'PAINAD-B':
            # Validate PAINAD-B specific fields
            for field in ['respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad']:
                if cleaned_data.get(field) is None:
                    self.add_error(field, f'Este campo é obrigatório para a escala PAINAD-B.')

        return cleaned_data
