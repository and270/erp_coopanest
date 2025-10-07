from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from agenda.models import ProcedimentoDetalhes, Convenios

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