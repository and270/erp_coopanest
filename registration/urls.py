from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_register_view, name='login_register'),
    path('cadastro/', views.cadastro_view, name='cadastro'),
    path('members/', views.members_view, name='members'),
    path('delete/<str:model_name>/<int:object_id>/', views.delete_view, name='delete'),
    path('profile/', views.profile_view, name='profile'),
    path('edit/<str:model_name>/<int:object_id>/', views.edit_view, name='edit'),
    path('profile/', views.profile_view, name='profile'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('termos-de-servico/', views.terms_of_service, name='terms_of_service'),
    path('politica-de-privacidade/', views.privacy_policy, name='privacy_policy'),
]