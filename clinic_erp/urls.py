from django.contrib import admin
from django.urls import path
from django.contrib.auth.views import LogoutView

from registration import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home_view, name='home'),
    path('login/', views.login_register_view, name='login_register'),
    path('cadastro/', views.cadastro_view, name='cadastro'),
    path('members/', views.members_view, name='members'),
    path('delete/<str:model_name>/<int:object_id>/', views.delete_view, name='delete'),
    path('profile/', views.profile_view, name='profile'),
    path('edit/<str:model_name>/<int:object_id>/', views.edit_view, name='edit'),
    path('profile/', views.profile_view, name='profile'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
]