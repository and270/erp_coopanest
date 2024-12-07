from django.db import models
from agenda.models import Procedimento
from django.utils.safestring import mark_safe

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

EVA_DESCRIPTIONS = {
        'low': 'Dor leve',
        'mid': 'Dor moderada',
        'high': 'Dor intensa'
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

    def __str__(self):
        return f"Avaliação RPA para {self.procedimento}"

    class Meta:
        verbose_name = "Avaliação RPA"
        verbose_name_plural = "Avaliações RPA"

class ProcedimentoQualidade(models.Model):
    SATISFACTION_CHOICES = [
        (1, 'Muito Insatisfeito'),
        (2, 'Insatisfeito'),
        (3, 'Neutro'),
        (4, 'Satisfeito'),
        (5, 'Muito Satisfeito'),
    ]

    EVENTOS_ADVERSOS_CHOICES = [
        ('broncoaspiracao', 'Broncoaspiração'),
        ('pcr', 'Parada Cardiorrespiratória (PCR)'),
        ('hemorragia', 'Hemorragia Maciça'),
        ('embolia', 'Embolia Pulmonar'),
        ('choque_anafilatico', 'Choque Anafilático'),
        ('lesao_orgao', 'Lesão de Órgão Não-Alvo'),
        ('iam', 'Infarto Agudo do Miocárdio'),
        ('avc', 'Acidente Vascular Cerebral (AVC)'),
        ('sirs', 'Síndrome da Resposta Inflamatória Sistêmica (SIRS)'),
        ('tvp', 'Trombose Venosa Profunda (TVP)'),
        ('ira', 'Insuficiência Renal Aguda'),
        ('pneumotorax', 'Pneumotórax'),
        ('sind_compartimental', 'Síndrome Compartimental'),
        ('hipertermia', 'Hipertermia Maligna'),
        ('deiscencia', 'Deiscência de Sutura'),
        ('lesao_nervo', 'Lesão de Nervo Periférico'),
        ('cegueira', 'Cegueira Pós-Operatória'),
        ('sdra', 'Síndrome do Desconforto Respiratório Agudo (SDRA)'),
        ('reacao_transfusional', 'Reação Transfusional Hemolítica Aguda'),
        ('sepse', 'Sepse Pós-Operatória'),
    ]

    ESCALA_CHOICES = [
        ('EVA', mark_safe('<span class="scale-name">EVA</span> &nbsp; &nbsp; &nbsp;Adultos e crianças maiores que 7 anos.')),
        ('FLACC', mark_safe('<span class="scale-name">FLACC</span> &nbsp; &nbsp; &nbsp;Crianças menores que 7 anos ou pacientes não verbais.')),
        ('BPS', mark_safe('<span class="scale-name">BPS</span> &nbsp; &nbsp; &nbsp;Pacientes intubados e sedados.')),
        ('PAINAD-B', mark_safe('<span class="scale-name">PAINAD-B</span> &nbsp; &nbsp; &nbsp;Pacientes com demência avançada.'))
    ]

    procedimento = models.OneToOneField(Procedimento, on_delete=models.CASCADE, related_name='qualidade')
    data_horario_inicio_efetivo = models.DateTimeField(verbose_name='Horário de Início Efetivo', null=True, blank=True)
    data_horario_fim_efetivo = models.DateTimeField(verbose_name='Horário de Término Efetivo', null=True, blank=True)
    
    # Adverse events fields
    eventos_adversos_graves = models.BooleanField(verbose_name='Eventos adversos graves', null=True, blank=True)
    eventos_adversos_graves_desc = models.CharField(
        max_length=50,
        choices=EVENTOS_ADVERSOS_CHOICES,
        verbose_name='Descrição do evento adverso grave',
        null=True,
        blank=True
    )
    reacao_alergica_grave = models.BooleanField(verbose_name='Reação alérgica grave', null=True, blank=True)
    reacao_alergica_grave_desc = models.TextField(verbose_name='Descrição da reação alérgica grave', null=True, blank=True)
    encaminhamento_uti = models.BooleanField(verbose_name='Encaminhamentos não programado à UTI', null=True, blank=True)
    evento_adverso_evitavel = models.BooleanField(verbose_name='Evento adverso evitável', null=True, blank=True)

    # Protocol adherence fields
    adesao_checklist = models.BooleanField(verbose_name='Adesão ao check list de segurança', null=True, blank=True)
    uso_tecnicas_assepticas = models.BooleanField(verbose_name='Uso adequado de técnicas assépticas', null=True, blank=True)
    conformidade_diretrizes = models.BooleanField(verbose_name='Conformidade com diretrizes e protocolos', null=True, blank=True)
    ponv = models.BooleanField(verbose_name='PONV', null=True, blank=True)
    adesao_profilaxia = models.BooleanField(verbose_name='Adesão aos protocolos de profilaxia antibiótica e de prevenção de TVP/TEP', null=True, blank=True)

    # Survey form fields
    satisfacao_geral = models.IntegerField(
        choices=SATISFACTION_CHOICES,
        null=True, 
        blank=True, 
        verbose_name='Satisfação geral'
    )
    clareza_informacoes = models.IntegerField(
        choices=SATISFACTION_CHOICES,
        null=True, 
        blank=True, 
        verbose_name='Clareza das informações'
    )
    comunicacao_disponibilidade = models.IntegerField(
        choices=SATISFACTION_CHOICES,
        null=True, 
        blank=True, 
        verbose_name='Comunicação e disponibilidade'
    )
    conforto_seguranca = models.IntegerField(
        choices=SATISFACTION_CHOICES,
        null=True, 
        blank=True, 
        verbose_name='Conforto e segurança'
    )
    comentario_adicional = models.TextField(
        blank=True, 
        null=True, 
        verbose_name='Comentário adicional'
    )
    csat_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name='CSAT Score'
    )

    # Pain evaluation fields (moved from Procedimento)
    dor_pos_operatoria = models.BooleanField(verbose_name="Dor pós operatória imediata", null=True, blank=True)
    escala = models.CharField(max_length=10, choices=ESCALA_CHOICES, verbose_name="Qual escala?", null=True, blank=True)
    
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

    class Meta:
        verbose_name = "Qualidade do Procedimento"
        verbose_name_plural = "Qualidade dos Procedimentos"
