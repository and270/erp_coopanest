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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['evento_adverso_qual'].widget.attrs.update({
            'rows': 3,
            'class': 'form-control form-options-text'
        })

    def clean(self):
        cleaned_data = super().clean()
        evento_adverso = cleaned_data.get('evento_adverso')
        evento_adverso_qual = cleaned_data.get('evento_adverso_qual')

        if evento_adverso and not evento_adverso_qual:
            self.add_error('evento_adverso_qual', 'Este campo é obrigatório quando há evento adverso.')

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
