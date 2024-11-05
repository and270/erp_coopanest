from django.utils import timezone
from django.db import models
from constants import CIRURGIA_PROCEDIMENTO, EXAME_PROCEDIMENTO, FORA_CENTRO_PROCEDIMENTO, PLANTONISTA_ESCALA, STATUS_FINISHED, STATUS_PENDING, SUBSTITUTO_ESCALA, FERIAS_ESCALA
from registration.models import Anesthesiologist, Surgeon, HospitalClinic, Groups
from django.contrib.postgres.fields import ArrayField
import uuid
from django.utils.safestring import mark_safe

class ProcedimentoDetalhes(models.Model):
    name = models.CharField(max_length=500, unique=True)

    def __str__(self):
        return self.name
    
class Procedimento(models.Model):

    PROCEDIMENTO_TYPE = (
        (CIRURGIA_PROCEDIMENTO , 'Cirurgia'),
        (FORA_CENTRO_PROCEDIMENTO , 'Procedimento Fora do Centro Cirúrgico'),
        (EXAME_PROCEDIMENTO , 'Exame'),
    )

    SATISFACTION_CHOICES = [
        (1, 'Muito Insatisfeito'),
        (2, 'Insatisfeito'),
        (3, 'Neutro'),
        (4, 'Satisfeito'),
        (5, 'Muito Satisfeito'),
    ]


    COBRANCA_CHOICES = [
        ('cooperativa', 'Cooperativa'),
        ('hospital', 'Hospital'),
        ('particular', 'Particular'),
    ]

    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    procedimento_type = models.CharField(
        max_length=40,
        default=CIRURGIA_PROCEDIMENTO,
        choices=PROCEDIMENTO_TYPE,
        verbose_name='Tipo de Procedimento',
    )
    nome_paciente = models.CharField(max_length=255, verbose_name='Nome do Paciente', default='')
    #telefone_paciente = models.CharField(max_length=20, verbose_name='Telefone do Paciente', blank=True, null=True)
    email_paciente = models.EmailField(verbose_name='Email do Paciente', blank=True, null=True)
    cpf_paciente = models.CharField(max_length=15, blank=True, null=True, verbose_name='CPF do Paciente')
    convenio = models.CharField(max_length=255, blank=True, null=True, verbose_name='Convênio')
    procedimento_principal = models.ForeignKey(
        ProcedimentoDetalhes,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Procedimento Principal'
    )
    data_horario = models.DateTimeField(verbose_name='Data e Horário Marcados', default=timezone.now)
    data_horario_fim = models.DateTimeField(verbose_name='Previsão de Término', default=timezone.now().replace(hour=20, minute=0, second=0, microsecond=0))
    hospital = models.ForeignKey(HospitalClinic, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Hospital/Clínica')
    outro_local = models.CharField(max_length=255, blank=True, null=True, verbose_name='Outro Local')
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cirurgião')
    anestesistas_responsaveis = models.ManyToManyField(
        Anesthesiologist,
        related_name='procedimentos',
        blank=True,
        verbose_name='Anestesistas Responsáveis'
    )
    nps_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True, null=True, blank=True)
    visita_pre_anestesica = models.BooleanField(default=False, verbose_name='Visita Pré-Anestésica Realizada')
    data_visita_pre_anestesica = models.DateField(blank=True, null=True, verbose_name='Data da Visita Pré-Anestésica')
    foto_anexo = models.ImageField(upload_to='anexos/', blank=True, null=True, verbose_name='Anexo Visita Pré-Anestésica')
    nome_responsavel_visita = models.CharField(max_length=255, blank=True, verbose_name='Nome do Responsável pela Visita', default='')
    
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
    comentario_adicional = models.TextField(blank=True, null=True, verbose_name='Comentário adicional')
    csat_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='CSAT Score')

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pendente'),
        (STATUS_FINISHED, 'Finalizado'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')

    #instâncias após a finalização do procedimento:
    ESCALA_CHOICES = [
        ('EVA', mark_safe('<span class="scale-name">EVA</span> &nbsp; &nbsp; &nbsp;Adultos e crianças maiores que 7 anos.')),
        ('FLACC', mark_safe('<span class="scale-name">FLACC</span> &nbsp; &nbsp; &nbsp;Crianças menores que 7 anos ou pacientes não verbais.')),
        ('BPS', mark_safe('<span class="scale-name">BPS</span> &nbsp; &nbsp; &nbsp;Pacientes intubados e sedados.')),
        ('PAINAD-B', mark_safe('<span class="scale-name">PAINAD-B</span> &nbsp; &nbsp; &nbsp;Pacientes com demência avançada.'))
    ]
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

    data_horario_inicio_efetivo = models.DateTimeField(verbose_name='Horário de Início Efetivo', null=True, blank=True)
    data_horario_fim_efetivo = models.DateTimeField(verbose_name='Horário de Término Efetivo', null=True, blank=True)
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
    
    eventos_adversos_graves = models.BooleanField(verbose_name='Eventos adversos graves (broncoaspiração, PCR, etc)', null=True, blank=True)
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
    adesao_checklist = models.BooleanField(verbose_name='Adesão ao check list de segurança', null=True, blank=True)
    uso_tecnicas_assepticas = models.BooleanField(verbose_name='Uso adequado de técnicas assépticas', null=True, blank=True)
    conformidade_diretrizes = models.BooleanField(verbose_name='Conformidade com diretrizes e protocolos', null=True, blank=True)
    ponv = models.BooleanField(verbose_name='PONV', null=True, blank=True)
    adesao_profilaxia = models.BooleanField(verbose_name='Adesão aos protocolos de profilaxia antibiótica e de prevenção de TVP/TEP', null=True, blank=True)
    tipo_cobranca = models.CharField(
        max_length=20,
        choices=COBRANCA_CHOICES,
        verbose_name='Cobrança via',
        null=True,
        blank=True
    )
    valor_cobranca = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Procedimento"
        verbose_name_plural = "Procedimentos"

    def __str__(self):
        return f'{self.procedimento} - {self.nome_paciente}'

class EscalaAnestesiologista(models.Model):

    ESCALA_TYPE = (
        (PLANTONISTA_ESCALA , 'Plantonista'),
        (SUBSTITUTO_ESCALA , 'Substituto'),
        (FERIAS_ESCALA , 'Férias/Licença'),
    )

    DIAS_DA_SEMANA = (
        ('0', 'Domingo'),
        ('1', 'Segunda-feira'),
        ('2', 'Terça-feira'),
        ('3', 'Quarta-feira'),
        ('4', 'Quinta-feira'),
        ('5', 'Sexta-feira'),
        ('6', 'Sábado'),
    )

    #mapeamento adapdatacao para primeiro dia da semana sendo Domingo
    python_weekday_to_dias_da_semana = {
            0: '1',  # Monday -> Segunda-feira
            1: '2',  # Tuesday -> Terça-feira
            2: '3',  # Wednesday -> Quarta-feira
            3: '4',  # Thursday -> Quinta-feira
            4: '5',  # Friday -> Sexta-feira
            5: '6',  # Saturday -> Sábado
            6: '0',  # Sunday -> Domingo
        }
    
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    escala_type = models.CharField(
        max_length=40,
        default=PLANTONISTA_ESCALA,
        choices=ESCALA_TYPE,
        verbose_name='Tipo de Escala',
    )
    anestesiologista = models.ForeignKey(Anesthesiologist, on_delete=models.CASCADE, verbose_name='Anestesiologista')
    data = models.DateField(verbose_name='Data da Escala', default=timezone.now)
    hora_inicio = models.TimeField(verbose_name='Hora de Início do Turno', default=timezone.now().replace(hour=8, minute=0, second=0, microsecond=0))
    hora_fim = models.TimeField(verbose_name='Hora de Fim do Turno', default=timezone.now().replace(hour=17, minute=0, second=0, microsecond=0))
    observacoes = models.TextField(blank=True, verbose_name='Observações', default='')
    
    class Meta:
        verbose_name = "Escala do Anestesiologista"
        verbose_name_plural = "Escalas dos Anestesiologistas"

    def __str__(self):
        return f'{self.anestesiologista.name} - {self.data.strftime("%d/%m/%Y %H:%M")}'
