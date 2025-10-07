from django.urls import path, re_path
from . import views

urlpatterns = [
    path('agenda/', views.agenda_view, name='agenda'),
    path('agenda/search/', views.search_agenda, name='search_agenda'),
    path('update-procedure/<int:procedure_id>/', views.update_procedure, name='update_procedure'),
    path('get-procedure/<int:procedure_id>/', views.get_procedure, name='get_procedure'),
    path('delete-procedure/<int:procedure_id>/', views.delete_procedure, name='delete_procedure'),
    path('create-procedure/', views.create_procedure, name='create_procedure'),
    path('procedure-autocomplete/', views.ProcedureAutocomplete.as_view(), name='procedure-autocomplete'),
    path('convenio-autocomplete/', views.ConvenioAutocomplete.as_view(), name='convenio-autocomplete'),
    path('escala/', views.escala_view, name='escala'),
    path('create-escala/', views.create_escala, name='create_escala'),
    path('update-escala/<int:escala_id>/', views.update_escala, name='update_escala'),
    path('get-escala/<int:escala_id>/', views.get_escala, name='get_escala'),
    path('delete-escala/<int:escala_id>/', views.delete_escala, name='delete_escala'),
    path('update-escala-date/<int:escala_id>/', views.update_escala_date, name='update_escala_date'),
    path('edit-single-day-escala/<int:escala_id>/', views.edit_single_day_escala, name='edit_single_day_escala'),
    re_path(r'^protected-media/(?P<file_path>.*)$', views.serve_protected_file, name='protected_file'),
    path('search-pacientes/', views.search_pacientes, name='search_pacientes'),
    path('survey/<uuid:nps_token>/', views.survey_view, name='survey'),
    path('agenda/import/', views.import_procedures, name='import_procedures'),
]
