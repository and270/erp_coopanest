from django.urls import path, re_path
from . import views

urlpatterns = [
    path('qualidade/', views.qualidade_view, name='qualidade'),
    path('qualidade/search/', views.search_qualidade, name='search_qualidade'),
    path('get-procedure/<int:procedure_id>/', views.get_procedure, name='get_procedure'),
    re_path(r'^protected-media/(?P<file_path>.*)$', views.serve_protected_file, name='protected_file'),
    path('search-pacientes/', views.search_pacientes, name='search_pacientes'),
    path('qualidade/avaliacao-rpa/<int:procedimento_id>/', views.avaliacao_rpa, name='avaliacao_rpa'),
    path('finalizar-procedimento/<int:procedimento_id>/', views.finalizar_procedimento, name='finalizar_procedimento'),
]
