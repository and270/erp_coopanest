from django.utils import timezone
from django.db import models
from constants import CIRURGIA_PROCEDIMENTO, EXAME_PROCEDIMENTO, FORA_CENTRO_PROCEDIMENTO
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
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.CASCADE, verbose_name='Cirurgião')
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
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    anestesiologista = models.ForeignKey(Anesthesiologist, on_delete=models.CASCADE, verbose_name='Anestesiologista')
    data_inicio = models.DateTimeField(verbose_name='Início do Turno')
    data_fim = models.DateTimeField(verbose_name='Fim do Turno')
    coringa = models.BooleanField(default=False, verbose_name='Coringa')
    fixo = models.BooleanField(default=False, verbose_name='Fixo')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    
    class Meta:
        verbose_name = "Escala do Anestesiologista"
        verbose_name_plural = "Escalas dos Anestesiologistas"

    def __str__(self):
        return f'{self.anestesiologista.name} - {self.data_inicio.strftime("%d/%m/%Y %H:%M")}'
