from django.db import models
from agenda.models import Procedimento
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce

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
        ('em_processamento', 'Em Processamento'),
        ('aguardando_pagamento', 'Aguardando Pagamento'),
        ('recurso_de_glosa', 'Recurso de Glosa'),
        ('processo_finalizado', 'Processo Finalizado'),
        ('cancelada', 'Cancelada'),
    ]

    procedimento = models.OneToOneField(Procedimento, on_delete=models.CASCADE, related_name='financas')
    tipo_cobranca = models.CharField(
        max_length=20,
        choices=COBRANCA_CHOICES,
        verbose_name='Cobrança via',
        null=True,
        blank=True
    )
    valor_faturado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor Faturado',
        null=True,
        blank=True
    )
    valor_recebido = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor Recebido',
        null=True,
        blank=True
    )
    valor_recuperado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor Recuperado (Glosa)',
        null=True,
        blank=True
    )
    valor_acatado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor A Recuperar',
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
        default='em_processamento',
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
        blank=True,
        db_index=True
    )

    class Meta:
        verbose_name = "Financeiro do Procedimento"
        verbose_name_plural = "Financeiro dos Procedimentos"

    def __str__(self):
        return f"Finanças - {self.procedimento}"

    def get_cpsa_display(self):
        if self.tipo_cobranca == 'cooperativa':
            return self.cpsa or "Não conciliado"
        return "--"

    @property
    def valor_total_recebido(self):
        return (self.valor_recebido or 0) + (self.valor_recuperado or 0)

    @property
    def valor_em_glosa(self):
        if self.status_pagamento == 'glosa' and self.valor_faturado is not None:
            return self.valor_faturado - self.valor_total_recebido
        elif self.status_pagamento == 'pago' and self.valor_faturado is not None and self.valor_faturado > self.valor_total_recebido:
            return self.valor_faturado - self.valor_total_recebido
        return 0

class Despesas(models.Model):
    group = models.ForeignKey(
        'registration.Groups',
        on_delete=models.SET_NULL,
        verbose_name='Grupo',
        null=True,
        blank=True
    )
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
    pago = models.BooleanField(
        default=False,
        verbose_name='Pago'
    )

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"

    def __str__(self):
        return f"Despesa - {self.descricao[:30]}"

class ConciliacaoTentativa(models.Model):
    procedimento_financas = models.ForeignKey(ProcedimentoFinancas, on_delete=models.CASCADE)
    cpsa_id = models.CharField(max_length=255)
    conciliado = models.BooleanField(null=True)
    data_tentativa = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('procedimento_financas', 'cpsa_id')
