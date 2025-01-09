from django.urls import path
from . import views

urlpatterns = [
    path('financas/', views.financas_view, name='financas'),
    path('financas/get-item/<str:type>/<int:id>/', views.get_finance_item, name='get-finance-item'),
    path('financas/update-item/', views.update_finance_item, name='update-finance-item'),
]