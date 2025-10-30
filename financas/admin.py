from django.contrib import admin
from financas.models import ProcedimentoFinancas, Despesas, DespesasRecorrentes, ConciliacaoTentativa

@admin.register(ProcedimentoFinancas)
class ProcedimentoFinancasAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'group', 'tipo_cobranca', 'status_pagamento', 'valor_faturado', 'data_pagamento')
    list_filter = ('group', 'tipo_cobranca', 'status_pagamento', 'data_pagamento')
    search_fields = ('cpsa', 'api_paciente_nome', 'procedimento__nome_paciente')
    readonly_fields = ('procedimento',)
    
    fieldsets = (
        ('Relacionamento', {
            'fields': ('procedimento', 'group')
        }),
        ('Cobrança', {
            'fields': ('tipo_cobranca', 'tipo_pagamento_direto')
        }),
        ('Valores', {
            'fields': ('valor_faturado', 'valor_recebido', 'valor_recuperado', 'valor_acatado')
        }),
        ('Status', {
            'fields': ('status_pagamento', 'data_pagamento')
        }),
        ('API / Dados Externos', {
            'fields': ('api_paciente_nome', 'api_data_cirurgia', 'api_hospital_nome', 'api_cooperado_nome', 'cpsa', 'matricula', 'senha'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Despesas)
class DespesasAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'group', 'valor', 'data', 'pago')
    list_filter = ('group', 'pago', 'data')
    search_fields = ('descricao', 'procedimento__nome_paciente')
    
@admin.register(DespesasRecorrentes)
class DespesasRecorrentesAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'group', 'valor', 'periodicidade', 'ativa', 'data_inicio')
    list_filter = ('group', 'periodicidade', 'ativa', 'data_inicio')
    search_fields = ('descricao',)

@admin.register(ConciliacaoTentativa)
class ConciliacaoTentativaAdmin(admin.ModelAdmin):
    list_display = ('procedimento_financas', 'cpsa_id', 'conciliado', 'data_tentativa')
    list_filter = ('conciliado', 'data_tentativa')
    search_fields = ('cpsa_id', 'procedimento_financas__cpsa')
    readonly_fields = ('data_tentativa',)
