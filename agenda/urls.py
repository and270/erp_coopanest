from django.urls import path
from . import views

urlpatterns = [
    path('agenda/', views.agenda_view, name='agenda'),
    path('update-procedure/<int:procedure_id>/', views.update_procedure, name='update_procedure'),
    path('get-procedure/<int:procedure_id>/', views.get_procedure, name='get_procedure'),
    path('delete-procedure/<int:procedure_id>/', views.delete_procedure, name='delete_procedure'),
    path('create-procedure/', views.create_procedure, name='create_procedure'),
    path('escala/', views.escala_view, name='escala'),
    path('create-escala/', views.create_escala, name='create_escala'),
    path('update-escala/<int:escala_id>/', views.update_escala, name='update_escala'),
    path('get-escala/<int:escala_id>/', views.get_escala, name='get_escala'),
]
