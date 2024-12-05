from django.db import models
from agenda.models import Procedimento

class ProcedimentoFinancas(models.Model):
    COBRANCA_CHOICES = [
        ('cooperativa', 'Cooperativa'),
        ('hospital', 'Hospital'),
        ('particular', 'Direta'),
    ]

    DIRECT_PAYMENT_CHOICES = [
        ('cartao', 'Cartão'),
        ('cheque', 'Cheque'),
        ('dinheiro', 'Dinheiro'),
        ('pix', 'Pix'),
        ('transferencia', 'Transferência'),
        ('boleto', 'Boleto'),
    ]

    procedimento = models.OneToOneField(Procedimento, on_delete=models.CASCADE, related_name='financas')
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
    tipo_pagamento_direto = models.CharField(
        max_length=20,
        choices=DIRECT_PAYMENT_CHOICES,
        verbose_name='Tipo de pagamento direto',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Financeiro do Procedimento"
        verbose_name_plural = "Financeiro dos Procedimentos"
