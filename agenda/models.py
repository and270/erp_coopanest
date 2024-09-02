from django.db import models
from registration.models import Anesthesiologist, Surgeon, HospitalClinic

class Procedimento(models.Model):
    nome_paciente = models.CharField(max_length=255, verbose_name='Nome do Paciente')
    procedimento = models.CharField(max_length=255, verbose_name='Procedimento')
    cirurgiao = models.ForeignKey(Surgeon, on_delete=models.CASCADE, verbose_name='Cirurgião')
    anestesista_responsavel = models.ForeignKey(Anesthesiologist, on_delete=models.CASCADE, verbose_name='Anestesista Responsável')
    data_horario = models.DateTimeField(verbose_name='Data e Horário Marcados')
    hospital = models.ForeignKey(HospitalClinic, on_delete=models.CASCADE, verbose_name='Hospital/Clínica')
    visita_pre_anestesica = models.BooleanField(default=False, verbose_name='Visita Pré-Anestésica Realizada')
    foto_anexo = models.ImageField(upload_to='anexos/', blank=True, null=True, verbose_name='Anexo de Foto')
    nome_responsavel_visita = models.CharField(max_length=255, blank=True, verbose_name='Nome do Responsável pela Visita')
    data_visita_pre_anestesica = models.DateField(blank=True, null=True, verbose_name='Data da Visita Pré-Anestésica')
    link_nps = models.URLField(blank=True, verbose_name='Link de Pesquisa de Satisfação')
    
    class Meta:
        verbose_name = "Procedimento"
        verbose_name_plural = "Procedimentos"

    def __str__(self):
        return f'{self.procedimento} - {self.nome_paciente}'

class EscalaAnestesiologista(models.Model):
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
