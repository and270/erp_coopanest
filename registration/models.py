from django.db import models
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.models import AbstractUser

from constants import ADMIN_USER, ANESTESISTA_USER, GESTOR_USER, SECRETARIA_USER

class CustomUser(AbstractUser):

    USER_TYPE = (
        (SECRETARIA_USER , 'Secretária'),
        (GESTOR_USER , 'Gestor'),
        (ANESTESISTA_USER , 'Anestesista'),
        (ADMIN_USER , 'Administrador do Sistema'),
    )

    groups = models.ManyToManyField(Group, blank=True, related_name="%(app_label)s_%(class)s_related")
    user_permissions = models.ManyToManyField(Permission, blank=True, related_name="%(app_label)s_%(class)s_related")

    user_type = models.CharField(
        max_length=40,
        default=ANESTESISTA_USER,
        choices=USER_TYPE,
    )

class Anesthesiologist(models.Model):
    user = models.OneToOneField(CustomUser, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=255, default='')
    date_of_birth = models.DateField(default='1970-01-01')
    cpf = models.CharField(max_length=15, unique=True, default='000.000.000-00')
    function = models.CharField(max_length=255, default='Anestesista')
    estado = models.CharField(max_length=2, unique=True, default='RJ')
    crm = models.CharField(max_length=20, unique=True, default='')
    rqe = models.CharField(max_length=20, unique=True, default='')
    phone = models.CharField(max_length=15, default='5521999999999')
    role_in_group = models.CharField(max_length=255, default='Membro')
    admission_date = models.DateField(default='1970-01-01')
    responsible_hours = models.CharField(max_length=50, default='N/A')

    def __str__(self):
        return self.name
    
class Surgeon(models.Model):
    name = models.CharField(max_length=255, default='')
    specialty = models.CharField(max_length=255, default='Cirurgião Geral')
    estado = models.CharField(max_length=2, unique=True, default='RJ')
    crm = models.CharField(max_length=20, unique=True, default='')
    rqe = models.CharField(max_length=20, unique=True, default='')
    phone = models.CharField(max_length=15, default='0000000000')
    notes = models.TextField(blank=True, default='No notes')

    def __str__(self):
        return self.name
    
class HospitalClinic(models.Model):
    name = models.CharField(max_length=255, default='')
    address = models.CharField(max_length=255, default='No address provided')
    surgery_center_phone = models.CharField(max_length=15, default='0000000000')
    hospital_phone = models.CharField(max_length=15, default='0000000000')

    def __str__(self):
        return self.name