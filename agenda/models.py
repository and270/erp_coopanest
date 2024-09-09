from django.utils import timezone
from django.db import models
from constants import CIRURGIA_PROCEDIMENTO, EXAME_PROCEDIMENTO, FORA_CENTRO_PROCEDIMENTO, PLANTONISTA_ESCALA, SUBSTITUTO_ESCALA, FERIAS_ESCALA
from registration.models import Anesthesiologist, Surgeon, HospitalClinic, Groups

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
    telefone_paciente = models.CharField(max_length=20, verbose_name='Telefone do Paciente', blank=True, null=True)
    email_paciente = models.EmailField(verbose_name='Email do Paciente', blank=True, null=True)
    procedimento = models.CharField(max_length=255, verbose_name='Procedimento', default='')
    data_horario = models.DateTimeField(verbose_name='Data e Horário Marcados', default=timezone.now)
    data_horario_fim = models.DateTimeField(verbose_name='Horário de Término', default=timezone.now().replace(hour=20, minute=0, second=0, microsecond=0))
    hospital = models.ForeignKey(HospitalClinic, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Hospital/Clínica')
    outro_local = models.CharField(max_length=255, blank=True, null=True, verbose_name='Outro Local')
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cirurgião')
    anestesista_responsavel = models.ForeignKey(Anesthesiologist, on_delete=models.CASCADE, verbose_name='Anestesista Responsável')
    link_nps = models.URLField(blank=True, null=True, verbose_name='Link de Pesquisa de Satisfação')
    visita_pre_anestesica = models.BooleanField(default=False, verbose_name='Visita Pré-Anestésica Realizada')
    data_visita_pre_anestesica = models.DateField(blank=True, null=True, verbose_name='Data da Visita Pré-Anestésica')
    foto_anexo = models.ImageField(upload_to='anexos/', blank=True, null=True, verbose_name='Anexo Visita Pré-Anestésica')
    nome_responsavel_visita = models.CharField(max_length=255, blank=True, verbose_name='Nome do Responsável pela Visita', default='')
    
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
        (1, 'Segunda-feira'),
        (2, 'Terça-feira'),
        (3, 'Quarta-feira'),
        (4, 'Quinta-feira'),
        (5, 'Sexta-feira'),
        (6, 'Sábado'),
        (7, 'Domingo'),
    )

    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    escala_type = models.CharField(
        max_length=40,
        default=PLANTONISTA_ESCALA,
        choices=ESCALA_TYPE,
        verbose_name='Tipo de Escala',
    )
    anestesiologista = models.ForeignKey(Anesthesiologist, on_delete=models.CASCADE, verbose_name='Anestesiologista')
    data_inicio = models.DateField(verbose_name='Início do Turno', default=timezone.now)
    data_fim = models.DateField(verbose_name='Fim do Turno', default=timezone.now)
    hora_inicio = models.TimeField(verbose_name='Hora de Início', default=timezone.now().replace(hour=8, minute=0, second=0, microsecond=0))
    hora_fim = models.TimeField(verbose_name='Hora de Fim', default=timezone.now().replace(hour=17, minute=0, second=0, microsecond=0))
    dias_da_semana = models.CharField(max_length=20, choices=DIAS_DA_SEMANA, verbose_name='Dias da Semana', default='1')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    
    class Meta:
        verbose_name = "Escala do Anestesiologista"
        verbose_name_plural = "Escalas dos Anestesiologistas"

    def __str__(self):
        return f'{self.anestesiologista.name} - {self.data_inicio.strftime("%d/%m/%Y %H:%M")}'
