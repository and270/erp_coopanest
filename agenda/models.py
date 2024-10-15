from django.utils import timezone
from django.db import models
from constants import CIRURGIA_PROCEDIMENTO, EXAME_PROCEDIMENTO, FORA_CENTRO_PROCEDIMENTO, PLANTONISTA_ESCALA, SUBSTITUTO_ESCALA, FERIAS_ESCALA
from registration.models import Anesthesiologist, Surgeon, HospitalClinic, Groups
from django.contrib.postgres.fields import ArrayField
import uuid

class Procedimento(models.Model):

    PROCEDIMENTO_TYPE = (
        (CIRURGIA_PROCEDIMENTO , 'Cirurgia'),
        (FORA_CENTRO_PROCEDIMENTO , 'Procedimento Fora do Centro Cirúrgico'),
        (EXAME_PROCEDIMENTO , 'Exame'),
    )

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
    cpf_paciente = models.CharField(max_length=15, default='000.000.000-00', verbose_name='CPF do Paciente')
    convenio = models.CharField(max_length=255, blank=True, null=True, verbose_name='Convênio')
    procedimento = models.CharField(max_length=255, verbose_name='Procedimento', default='')
    data_horario = models.DateTimeField(verbose_name='Data e Horário Marcados', default=timezone.now)
    data_horario_fim = models.DateTimeField(verbose_name='Previsão de Término', default=timezone.now().replace(hour=20, minute=0, second=0, microsecond=0))
    hospital = models.ForeignKey(HospitalClinic, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Hospital/Clínica')
    outro_local = models.CharField(max_length=255, blank=True, null=True, verbose_name='Outro Local')
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cirurgião')
    anestesista_responsavel = models.ForeignKey(Anesthesiologist, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Anestesista Responsável')
    nps_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True, null=True, blank=True)
    visita_pre_anestesica = models.BooleanField(default=False, verbose_name='Visita Pré-Anestésica Realizada')
    data_visita_pre_anestesica = models.DateField(blank=True, null=True, verbose_name='Data da Visita Pré-Anestésica')
    foto_anexo = models.ImageField(upload_to='anexos/', blank=True, null=True, verbose_name='Anexo Visita Pré-Anestésica')
    nome_responsavel_visita = models.CharField(max_length=255, blank=True, verbose_name='Nome do Responsável pela Visita', default='')
    
    # New survey fields
    SATISFACTION_CHOICES = [
        (1, 'Muito Insatisfeito'),
        (2, 'Insatisfeito'),
        (3, 'Neutro'),
        (4, 'Satisfeito'),
        (5, 'Muito Satisfeito'),
    ]
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
