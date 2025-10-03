from django.utils import timezone
from django.db import models
from constants import (
    PLANTONISTA_ESCALA, STATUS_FINISHED, STATUS_PENDING, SUBSTITUTO_ESCALA, FERIAS_ESCALA,
    CONSULTA_PROCEDIMENTO, CIRURGIA_AMBULATORIAL_PROCEDIMENTO, CLINIC_TYPE_CHOICES
)
from registration.models import Anesthesiologist, Surgeon, HospitalClinic, Groups
import uuid

class ProcedimentoDetalhes(models.Model):
    name = models.CharField(max_length=500)
    codigo_procedimento = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name="ID do Procedimento")

    def __str__(self):
        return f"{self.name} ({self.codigo_procedimento})"
    
class Convenios(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Convênio"
        verbose_name_plural = "Convênios"

class Procedimento(models.Model):
    PROCEDIMENTO_TYPE = (
        (CONSULTA_PROCEDIMENTO, 'Consulta'),
        (CIRURGIA_AMBULATORIAL_PROCEDIMENTO, 'Cirurgia / Procedimento ambulatorial'),
    )

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pendente'),
        (STATUS_FINISHED, 'Finalizado'),
    )

    TIPO_PROCEDIMENTO_CHOICES = (
        ('urgencia', 'Urgência'),
        ('eletiva', 'Eletiva'),
    )

    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    procedimento_type = models.CharField(
        max_length=40,
        default=CIRURGIA_AMBULATORIAL_PROCEDIMENTO,
        choices=PROCEDIMENTO_TYPE,
        verbose_name='Tipo de Procedimento',
    )
    nome_paciente = models.CharField(max_length=255, verbose_name='Nome do Paciente', default='')
    #telefone_paciente = models.CharField(max_length=20, verbose_name='Telefone do Paciente', blank=True, null=True)
    email_paciente = models.EmailField(verbose_name='Email do Paciente', blank=True, null=True)
    cpf_paciente = models.CharField(max_length=15, blank=True, null=True, verbose_name='CPF do Paciente')
    convenio = models.ForeignKey(
        Convenios,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Convênio'
    )
    procedimento_principal = models.ForeignKey(
        ProcedimentoDetalhes,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Procedimento Principal'
    )
    data_horario = models.DateTimeField(verbose_name='Data e Horário Marcados', default=timezone.now)
    data_horario_fim = models.DateTimeField(verbose_name='Previsão de Término', null=True, blank=True)
    hospital = models.ForeignKey(HospitalClinic, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Hospital/Clínica')
    outro_local = models.CharField(max_length=255, blank=True, null=True, verbose_name='Outro Local')
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cirurgião (selecionar se cadastrado no sistema)')
    cirurgiao_nome = models.CharField(max_length=255, blank=True, null=True, verbose_name='Nome do Cirurgião (Se não cadastrado)')
    # Legacy relation kept for backward compatibility. New model fields below handle
    # a single Cooperado and a free-text list of Anestesistas.
    anestesistas_responsaveis = models.ManyToManyField(
        Anesthesiologist,
        related_name='procedimentos',
        blank=True,
        verbose_name='Anestesistas Responsáveis'
    )
    cooperado = models.ForeignKey(
        Anesthesiologist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='procedimentos_como_cooperado',
        verbose_name='Cooperado'
    )
    anestesistas_livres = models.TextField(
        default='',
        blank=True,
        verbose_name='Anestesistas (livre)'
    )
    nps_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True, null=True, blank=True)
    visita_pre_anestesica = models.BooleanField(default=False, verbose_name='Visita Pré-Anestésica Realizada')
    data_visita_pre_anestesica = models.DateField(blank=True, null=True, verbose_name='Data da Visita Pré-Anestésica')
    foto_anexo = models.ImageField(upload_to='anexos/', blank=True, null=True, verbose_name='Anexo Visita Pré-Anestésica')
    nome_responsavel_visita = models.CharField(max_length=255, blank=True, verbose_name='Nome do Responsável pela Visita', default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name='Status')
    tipo_procedimento = models.CharField(
        max_length=10,
        choices=TIPO_PROCEDIMENTO_CHOICES,
        verbose_name='Eletiva ou Urgência',
        default='eletiva', # Default to 'eletiva' or choose another appropriate default
        null=True, blank=True # Allow null and blank temporarily if procedures can exist without this info initially
    )

    # New optional field for surgical profile clinic type
    tipo_clinica = models.CharField(
        max_length=50,
        choices=CLINIC_TYPE_CHOICES,
        verbose_name='Clínica (Perfil Cirúrgico)',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Procedimento"
        verbose_name_plural = "Procedimentos"

    def __str__(self):
        return f'{self.procedimento_principal} - {self.nome_paciente}'

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