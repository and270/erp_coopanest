from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from agenda.models import ProcedimentoDetalhes, Convenios

# Register your models here.
@admin.register(ProcedimentoDetalhes)
class ProcedimentoDetalhesAdmin(ImportExportModelAdmin):
    pass

@admin.register(Convenios)
class ConveniosAdmin(ImportExportModelAdmin):
    pass