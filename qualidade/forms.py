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
            'tempo_alta_rpa': forms.TimeInput(attrs={'type': 'time'}),
            'dor_pos_operatoria': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')]),
            'escala': forms.RadioSelect(),
            'eva_score': forms.NumberInput(attrs={'min': 1, 'max': 10}),
            'evento_adverso': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')]),
            'ponv': forms.RadioSelect(choices=[(True, 'Sim'), (False, 'Não')]),
            'face': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'pernas': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'atividade': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'choro': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'consolabilidade': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'expressao_facial': forms.NumberInput(attrs={'min': 1, 'max': 4}),
            'movimentos_membros_superiores': forms.NumberInput(attrs={'min': 1, 'max': 4}),
            'adaptacao_ventilador': forms.NumberInput(attrs={'min': 1, 'max': 4}),
            'respiracao': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'vocalizacao_negativa': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'expressao_facial_painad': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'linguagem_corporal': forms.NumberInput(attrs={'min': 0, 'max': 2}),
            'consolabilidade_painad': forms.NumberInput(attrs={'min': 0, 'max': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['evento_adverso_qual'].widget.attrs['rows'] = 3

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
