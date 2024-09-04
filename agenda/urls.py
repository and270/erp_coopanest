from django.urls import path
from . import views

urlpatterns = [
    path('agenda/', views.agenda_view, name='agenda'),
    path('get_procedimento_form/', views.get_procedimento_form, name='get_procedimento_form'),
]
