from django.urls import path
from . import views

urlpatterns = [
    path('procedimentos/', views.agenda_procedimentos_view, name='agenda_procedimentos'),
    path('procedimentos/add/', views.add_procedimento_view, name='add_procedimento'),
    path('escala/', views.escala_trabalho_view, name='escala_trabalho'),
    path('escala/add/', views.add_escala_view, name='add_escala'),
]
