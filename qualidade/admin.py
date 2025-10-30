from django.contrib import admin
from qualidade.models import AvaliacaoRPA, ProcedimentoQualidade

@admin.register(AvaliacaoRPA)
class AvaliacaoRPAAdmin(admin.ModelAdmin):
    list_display = ('procedimento', 'dor_pos_operatoria', 'escala', 'tempo_alta_rpa')
    list_filter = ('dor_pos_operatoria', 'escala', 'evento_adverso', 'ponv')
    search_fields = ('procedimento__nome_paciente',)
    readonly_fields = ('procedimento',)

@admin.register(ProcedimentoQualidade)
class ProcedimentoQualidadeAdmin(admin.ModelAdmin):
    list_display = ('procedimento', 'eventos_adversos_graves', 'evento_adverso_evitavel', 'satisfacao_geral', 'csat_score')
    list_filter = ('eventos_adversos_graves', 'evento_adverso_evitavel', 'encaminhamento_uti', 'data_horario_inicio_efetivo')
    search_fields = ('procedimento__nome_paciente',)
    readonly_fields = ('procedimento',)
    
    fieldsets = (
        ('Procedimento', {
            'fields': ('procedimento',)
        }),
        ('Horários', {
            'fields': ('data_horario_inicio_efetivo', 'data_horario_fim_efetivo')
        }),
        ('Eventos Adversos Graves', {
            'fields': ('eventos_adversos_graves', 'eventos_adversos_graves_desc', 'reacao_alergica_grave', 'reacao_alergica_grave_desc', 'encaminhamento_uti'),
            'classes': ('collapse',)
        }),
        ('Eventos Adversos Evitáveis', {
            'fields': ('evento_adverso_evitavel', 'evento_adverso_evitavel_desc'),
            'classes': ('collapse',)
        }),
        ('Protocolos e Conformidade', {
            'fields': ('adesao_checklist', 'uso_tecnicas_assepticas', 'conformidade_diretrizes', 'adesao_profilaxia_antibiotica', 'adesao_prevencao_tvp_tep', 'ponv'),
            'classes': ('collapse',)
        }),
        ('Satisfação (CSAT)', {
            'fields': ('satisfacao_geral', 'clareza_informacoes', 'comunicacao_disponibilidade', 'conforto_seguranca', 'comentario_adicional', 'csat_score'),
            'classes': ('collapse',)
        }),
        ('Dor Pós-Operatória', {
            'fields': ('dor_pos_operatoria', 'escala', 'eva_score', 'face', 'pernas', 'atividade', 'choro', 'consolabilidade', 'expressao_facial', 'movimentos_membros_superiores', 'adaptacao_ventilador', 'respiracao', 'vocalizacao_negativa', 'expressao_facial_painad', 'linguagem_corporal', 'consolabilidade_painad'),
            'classes': ('collapse',)
        }),
        ('Jejum e Aldrete', {
            'fields': ('abreviacao_jejum', 'escala_aldrete'),
            'classes': ('collapse',)
        }),
    )