from django.db import models
from agenda.models import Procedimento
from django.utils.safestring import mark_safe


class AvaliacaoRPA(models.Model):
    ESCALA_CHOICES = [
        ('EVA', mark_safe('<span class="scale-name">EVA</span> &nbsp; &nbsp; &nbsp;Adultos e crianças maiores que 7 anos.')),
        ('FLACC', mark_safe('<span class="scale-name">FLACC</span> &nbsp; &nbsp; &nbsp;Crianças menores que 7 anos ou pacientes não verbais.')),
        ('BPS', mark_safe('<span class="scale-name">BPS</span> &nbsp; &nbsp; &nbsp;Pacientes intubados e sedados.')),
        ('PAINAD-B', mark_safe('<span class="scale-name">PAINAD-B</span> &nbsp; &nbsp; &nbsp;Pacientes com demência avançada.'))
    ]

    procedimento = models.OneToOneField(Procedimento, on_delete=models.CASCADE, related_name='avaliacao_rpa')
    tempo_alta_rpa = models.TimeField(verbose_name="Tempo até atingir alta RPA")
    dor_pos_operatoria = models.BooleanField(verbose_name="Dor pós operatória imediata")
    escala = models.CharField(max_length=10, choices=ESCALA_CHOICES, verbose_name="Qual escala?")
    
    # EVA specific fields
    eva_score = models.IntegerField(verbose_name="Quanto?", null=True, blank=True)
    
    # FLACC specific fields
    face = models.IntegerField(verbose_name="Face", null=True, blank=True)
    pernas = models.IntegerField(verbose_name="Pernas", null=True, blank=True)
    atividade = models.IntegerField(verbose_name="Atividade", null=True, blank=True)
    choro = models.IntegerField(verbose_name="Choro", null=True, blank=True)
    consolabilidade = models.IntegerField(verbose_name="Consolabilidade", null=True, blank=True)
    
    # BPS specific fields
    expressao_facial = models.IntegerField(verbose_name="Expressão facial", null=True, blank=True)
    movimentos_membros_superiores = models.IntegerField(verbose_name="Movimentos dos membros superiores", null=True, blank=True)
    adaptacao_ventilador = models.IntegerField(verbose_name="Adaptação ao ventilador mecânico", null=True, blank=True)
    
    # PAINAD-B specific fields
    respiracao = models.IntegerField(verbose_name="Respiração", null=True, blank=True)
    vocalizacao_negativa = models.IntegerField(verbose_name="Vocalização negativa", null=True, blank=True)
    expressao_facial_painad = models.IntegerField(verbose_name="Expressão facial", null=True, blank=True)
    linguagem_corporal = models.IntegerField(verbose_name="Linguagem corporal", null=True, blank=True)
    consolabilidade_painad = models.IntegerField(verbose_name="Consolabilidade", null=True, blank=True)

    # Common fields
    evento_adverso = models.BooleanField(verbose_name="Evento adverso evitável na RPA", null=True, blank=True)
    evento_adverso_qual = models.TextField(verbose_name="Qual?", null=True, blank=True)
    ponv = models.BooleanField(verbose_name="PONV na RPA", null=True, blank=True)

    EVA_DESCRIPTIONS = {
        'low': 'Dor leve',
        'mid': 'Dor moderada',
        'high': 'Dor intensa'
    }

    FLACC_DESCRIPTIONS = {
        'face': {
            'low': 'Nenhuma expressão particular ou sorriso',
            'mid': 'Caretas ou sobrancelhas franzidas de vez em quando, introversão, desinteresse',
            'high': 'Tremor frequente do queixo, mandíbulas cerradas'
        },
        'pernas': {
            'low': 'Posição normal ou relaxadas',
            'mid': 'Inquietas, agitadas, tensas',
            'high': 'Chutando ou esticadas'
        },
        'atividade': {
            'low': 'Quieto, posição normal, movendo-se facilmente',
            'mid': 'Contorcendo-se, movendo-se para frente e para trás, tenso',
            'high': 'Curvado, rígido ou com movimentos bruscos'
        },
        'choro': {
            'low': 'Sem choro (acordado ou dormindo)',
            'mid': 'Gemidos ou choramingos; queixa ocasional',
            'high': 'Choro continuado, grito ou soluço; queixa com frequência'
        },
        'consolabilidade': {
            'low': 'Satisfeito, relaxado',
            'mid': 'Tranquilizado por toques, abraços ou conversas ocasionais; pode ser distraído',
            'high': 'Difícil de consolar ou confortar'
        }
    }

    BPS_DESCRIPTIONS = {
        'expressao_facial': {
            'low': 'Relaxada',
            'mid': 'Parcialmente tensa',
            'high': 'Totalmente tensa',
            'extreme': 'Fazendo careta'
        },
        'movimentos_membros_superiores': {
            'low': 'Sem movimentos',
            'mid': 'Parcialmente fletidos',
            'high': 'Totalmente fletidos',
            'extreme': 'Permanentemente retraídos'
        },
        'adaptacao_ventilador': {
            'low': 'Tolerando movimentos',
            'mid': 'Tossindo, mas tolerando',
            'high': 'Lutando contra o ventilador',
            'extreme': 'Impossibilidade de controle'
        }
    }

    PAINAD_B_DESCRIPTIONS = {
        'respiracao': {
            'low': 'Normal',
            'mid': 'Dificuldade ocasional na respiração. Curto período de hiperventilação',
            'high': 'Respiração ruidosa e com dificuldade. Longo período de hiperventilação. Respiração Cheyne-Stokes'
        },
        'vocalizacao_negativa': {
            'low': 'Nenhuma',
            'mid': 'Resmungos ou gemidos ocasionais. Fala baixa com qualidade negativa ou desaprovadora',
            'high': 'Chamados perturbadores repetitivos. Resmungos ou gemidos altos. Choro'
        },
        'expressao_facial_painad': {
            'low': 'Sorridente ou inexpressiva',
            'mid': 'Triste, Amedrontada, Franzida',
            'high': 'Careta'
        },
        'linguagem_corporal': {
            'low': 'Relaxada',
            'mid': 'Tensa, Andar angustiado de um lado para outro, Inquietação',
            'high': 'Rígida, Punhos cerrados, Joelhos encolhidos, Puxar ou empurrar, Agitação'
        },
        'consolabilidade_painad': {
            'low': 'Sem necessidade de consolar',
            'mid': 'Distraído ou tranquilizado por voz ou toque',
            'high': 'Impossível consolar, distrair ou tranquilizar'
        }
    }

    def __str__(self):
        return f"Avaliação RPA para {self.procedimento}"

    class Meta:
        verbose_name = "Avaliação RPA"
        verbose_name_plural = "Avaliações RPA"
