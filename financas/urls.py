from django.urls import path
from . import views

urlpatterns = [
    path('financas/', views.financas_view, name='financas'),
    path('financas/get-item/<str:type>/<int:id>/', views.get_finance_item, name='get-finance-item'),
    path('financas/update-item/', views.update_finance_item, name='update-finance-item'),
    path('financas/create-item/', views.create_finance_item, name='create_finance_item'),
    path('financas/create-receita/', views.create_receita_item, name='create_receita_item'),
    path('financas/export/', views.export_finances, name='export_finances'),
    path('financas/delete-item/', views.delete_finance_item, name='delete_finance_item'),
    path('financas/conciliar/', views.conciliar_financas, name='conciliar_financas'),
    # Despesas Recorrentes URLs
    path('financas/get-despesa-recorrente/<int:id>/', views.get_despesa_recorrente_item, name='get-despesa-recorrente-item'),
    path('financas/create-despesa-recorrente/', views.create_despesa_recorrente_item, name='create_despesa_recorrente_item'),
    path('financas/update-despesa-recorrente/', views.update_despesa_recorrente_item, name='update_despesa_recorrente_item'),
    path('financas/delete-despesa-recorrente/', views.delete_despesa_recorrente_item, name='delete_despesa_recorrente_item'),
]