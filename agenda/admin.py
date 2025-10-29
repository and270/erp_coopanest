from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from agenda.models import ProcedimentoDetalhes, Convenios, Procedimento, EscalaAnestesiologista

class ProcedimentoDetalhesResource(resources.ModelResource):
    class Meta:
        model = ProcedimentoDetalhes
        fields = ('id', 'name', 'codigo_procedimento')
        export_order = ('id', 'name', 'codigo_procedimento')
        import_id_fields = ['codigo_procedimento']
        skip_unchanged = True
        report_skipped = True

# Register your models here.
@admin.register(ProcedimentoDetalhes)
class ProcedimentoDetalhesAdmin(ImportExportModelAdmin):
    resource_class = ProcedimentoDetalhesResource
    list_display = ('name', 'codigo_procedimento')
    search_fields = ('name', 'codigo_procedimento')

@admin.register(Convenios)
class ConveniosAdmin(ImportExportModelAdmin):
    pass

@admin.register(Procedimento)
class ProcedimentoAdmin(admin.ModelAdmin):
    list_display = ('nome_paciente', 'procedimento_principal', 'group', 'data_horario', 'status')
    list_filter = ('group', 'status', 'procedimento_type', 'data_horario')
    search_fields = ('nome_paciente', 'cpf_paciente', 'email_paciente')
    readonly_fields = ('nps_token',)
    
    fieldsets = (
        ('Informações do Procedimento', {
            'fields': ('group', 'procedimento_type', 'tipo_procedimento', 'procedimento_principal', 'status')
        }),
        ('Dados do Paciente', {
            'fields': ('nome_paciente', 'cpf_paciente', 'email_paciente')
        }),
        ('Equipe Médica', {
            'fields': ('cirurgiao', 'cirurgiao_nome', 'cooperado', 'anestesistas_responsaveis', 'anestesistas_livres')
        }),
        ('Local do Procedimento', {
            'fields': ('hospital', 'outro_local', 'convenio')
        }),
        ('Agendamento', {
            'fields': ('data_horario', 'data_horario_fim')
        }),
        ('Visita Pré-Anestésica', {
            'fields': ('visita_pre_anestesica', 'data_visita_pre_anestesica', 'foto_anexo', 'nome_responsavel_visita'),
            'classes': ('collapse',)
        }),
        ('Outros', {
            'fields': ('tipo_clinica', 'nps_token'),
            'classes': ('collapse',)
        }),
    )

@admin.register(EscalaAnestesiologista)
class EscalaAnestesiologistaAdmin(admin.ModelAdmin):
    list_display = ('anestesiologista', 'group', 'escala_type', 'data', 'hora_inicio', 'hora_fim')
    list_filter = ('group', 'escala_type', 'data')
    search_fields = ('anestesiologista__name', 'observacoes')
    ordering = ('-data',)