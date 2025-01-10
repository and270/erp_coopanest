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

    STATUS_PAGAMENTO_CHOICES = [
        ('pago', 'Pago'),
        ('pendente', 'Em Andamento'),
        ('glosa', 'Glosa'),
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
    status_pagamento = models.CharField(
        max_length=20,
        choices=STATUS_PAGAMENTO_CHOICES,
        default='pendente',
        verbose_name='Status do Pagamento'
    )
    data_pagamento = models.DateField(
        verbose_name='Data do pagamento',
        null=True,
        blank=True
    )
    cpsa = models.CharField(
        max_length=255,
        verbose_name='CPSA',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Financeiro do Procedimento"
        verbose_name_plural = "Financeiro dos Procedimentos"

    def __str__(self):
        return f"Finanças - {self.procedimento}"

class Despesas(models.Model):
    STATUS_CHOICES = [
        ('a_vencer', 'A Vencer'),
        ('pago', 'Pago'),
        ('atrasado', 'Pagamento Atrasado'),
    ]

    procedimento = models.OneToOneField(
        Procedimento, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True,
        related_name='despesa'
    )
    valor = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor'
    )
    data = models.DateField(verbose_name='Data')
    descricao = models.TextField(verbose_name='Descrição')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='a_vencer',
        verbose_name='Status'
    )

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"

    def __str__(self):
        return f"Despesa - {self.descricao[:30]}"
