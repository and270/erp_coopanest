from django.urls import path
from . import views

urlpatterns = [
    path('agenda/', views.agenda_view, name='agenda'),
]
