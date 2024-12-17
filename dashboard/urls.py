from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard-financas/', views.financas_dashboard_view, name='financas_dashboard_view'),
    path('export-financas/', views.export_financas_excel, name='export_financas_excel'),
]
