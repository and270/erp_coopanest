from django.urls import path, re_path
from . import views

urlpatterns = [
    path('financas/', views.financas_view, name='financas'),
]