from django.db import models
from agenda.models import Procedimento
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from registration.models import Groups

class ProcedimentoFinancas(models.Model):
    COBRANCA_CHOICES = [
        ('cooperativa', 'Cooperativa'),
        ('hospital', 'Hospital'),
        ('coi', 'COI'),
        ('amil', 'Amil'),
        ('particular', 'Direta'),
        ('via_cirurgiao', 'Via Cirurgião'),
        ('cortesia', 'Cortesia'),
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

    procedimento = models.ForeignKey(
        Procedimento, 
        on_delete=models.SET_NULL, 
        related_name='financas_records',
        null=True,
        blank=True
    )
    group = models.ForeignKey(
        Groups,
        on_delete=models.SET_NULL,
        verbose_name='Grupo',
        null=True,
        blank=True
    )
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
    
    api_paciente_nome = models.CharField(
        max_length=255, 
        verbose_name='Nome Paciente (API)', 
        null=True, 
        blank=True
    )
    api_data_cirurgia = models.DateField(
        verbose_name='Data Cirurgia (API)', 
        null=True, 
        blank=True
    )
    api_hospital_nome = models.CharField(
        max_length=255, 
        verbose_name='Hospital (API)', 
        null=True, 
        blank=True
    )
    api_cooperado_nome = models.CharField(
        max_length=255, 
        verbose_name='Cooperado (API)', 
        null=True, 
        blank=True
    )
    matricula = models.CharField(
        max_length=255,
        verbose_name='Matrícula',
        null=True,
        blank=True
    )
    senha = models.CharField(
        max_length=255,
        verbose_name='Senha',
        null=True,
        blank=True
    )
    plantao_eletiva = models.CharField(
        max_length=255,
        verbose_name='Plantão/Eletiva (API)',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Financeiro do Procedimento"
        verbose_name_plural = "Financeiro dos Procedimentos"
        constraints = [
            models.UniqueConstraint(
                fields=['procedimento', 'cpsa'], 
                name='unique_cpsa_per_procedure',
                condition=models.Q(procedimento__isnull=False, cpsa__isnull=False)
            )
        ]

    def __str__(self):
        if self.procedimento:
            return f"Finanças (Vinculado) - {self.procedimento} - CPSA: {self.cpsa or 'N/A'}"
        elif self.api_paciente_nome:
            return f"Finanças (Não Vinculado) - {self.api_paciente_nome} ({self.cpsa or 'Sem CPSA'})"
        else:
            return f"Finanças (Não Vinculado) - ID: {self.id}"

    def get_cpsa_display(self):
        if self.tipo_cobranca == 'cooperativa':
            return self.cpsa or "Não conciliado"
        return "--"

    @property
    def valor_total_recebido(self):
        return (self.valor_recebido or 0) + (self.valor_recuperado or 0)

    @property
    def valor_em_glosa(self):
        is_glosa_status = self.status_pagamento in ['recurso_de_glosa']
        is_paid_short = self.status_pagamento == 'processo_finalizado' and self.valor_faturado is not None and self.valor_faturado > self.valor_total_recebido

        if (is_glosa_status or is_paid_short) and self.valor_faturado is not None:
            total_recebido = self.valor_total_recebido or 0
            glosa = self.valor_faturado - total_recebido
            return glosa if glosa > 0 else 0
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

class DespesasRecorrentes(models.Model):
    PERIODICIDADE_CHOICES = [
        ('diaria', 'Diária'),
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
    ]

    group = models.ForeignKey(
        'registration.Groups',
        on_delete=models.SET_NULL,
        verbose_name='Grupo',
        null=True,
        blank=True
    )
    descricao = models.TextField(verbose_name='Descrição')
    valor = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Valor'
    )
    periodicidade = models.CharField(
        max_length=20,
        choices=PERIODICIDADE_CHOICES,
        verbose_name='Periodicidade'
    )
    data_inicio = models.DateField(verbose_name='Data de Início')
    ativa = models.BooleanField(
        default=True,
        verbose_name='Ativa'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Despesa Recorrente"
        verbose_name_plural = "Despesas Recorrentes"
        ordering = ['-data_inicio', '-criado_em']

    def __str__(self):
        return f"Despesa Recorrente - {self.descricao[:30]} ({self.get_periodicidade_display()})"

    def get_periodicidade_display_short(self):
        """Retorna versão abreviada da periodicidade para exibição em tabelas"""
        mapping = {
            'diaria': 'Diária',
            'semanal': 'Semanal',
            'quinzenal': 'Quinz.',
            'mensal': 'Mensal',
            'semestral': 'Semest.',
            'anual': 'Anual',
        }
        return mapping.get(self.periodicidade, self.get_periodicidade_display())

class ConciliacaoTentativa(models.Model):
    procedimento_financas = models.ForeignKey(ProcedimentoFinancas, on_delete=models.CASCADE)
    cpsa_id = models.CharField(max_length=255)
    conciliado = models.BooleanField(null=True)
    data_tentativa = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('procedimento_financas', 'cpsa_id')


class ConciliacaoJob(models.Model):
    """Tracks background conciliation jobs for async processing."""
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('running', 'Em Execução'),
        ('completed', 'Concluído'),
        ('failed', 'Falhou'),
    ]
    
    group = models.ForeignKey(Groups, on_delete=models.CASCADE, related_name='conciliacao_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Progress tracking
    total_guias = models.IntegerField(default=0)
    processed_count = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    linked_count = models.IntegerField(default=0)
    
    # Status message for UI
    current_step = models.CharField(max_length=255, default='Iniciando...')
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Conciliação {self.group.name} - {self.status} ({self.started_at})"
    
    @property
    def progress_percent(self):
        if self.total_guias == 0:
            return 0
        return int((self.processed_count / self.total_guias) * 100)

