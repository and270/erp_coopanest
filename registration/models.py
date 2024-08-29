from django.db import models
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from constants import ADMIN_USER, ANESTESISTA_USER, GESTOR_USER, SECRETARIA_USER

class Groups(models.Model):
    name = models.CharField(max_length=255, verbose_name='Nome do Grupo')

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"

    def __str__(self):
        return self.name
    
class CustomUser(AbstractUser):
    USER_TYPE = (
        (SECRETARIA_USER , 'Secretária'),
        (GESTOR_USER , 'Gestor'),
        (ANESTESISTA_USER , 'Anestesista'),
    )

    groups = models.ManyToManyField(Group, blank=True, related_name="%(app_label)s_%(class)s_related")
    user_permissions = models.ManyToManyField(Permission, blank=True, related_name="%(app_label)s_%(class)s_related")
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)

    user_type = models.CharField(
        max_length=40,
        default=ANESTESISTA_USER,
        choices=USER_TYPE,
        verbose_name='Tipo de usuário',
    )
    validado = models.BooleanField(default=False, verbose_name='Validado') 

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email  # Set the username to the email if it's empty
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

class Anesthesiologist(models.Model):
    ROLE_CHOICES = [
        ('administrador', 'Administrador'),
        ('gestor', 'Gestor'),
        ('rotina', 'Rotina'),
        ('plantonista', 'Plantonista'),
        ('coringa', 'Coringa')
    ]

    user = models.OneToOneField(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Usuário')
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    name = models.CharField(max_length=255, default='', verbose_name='Nome')
    date_of_birth = models.DateField(default='1970-01-01', verbose_name='Data de Nascimento')
    cpf = models.CharField(max_length=15, unique=True, default='000.000.000-00', verbose_name='CPF')
    function = models.CharField(max_length=255, default='Anestesista', verbose_name='Função')
    estado = models.CharField(max_length=2, default='RJ', verbose_name='Estado')
    crm = models.CharField(max_length=20, unique=True, default='', verbose_name='CRM')
    phone = models.CharField(max_length=15, default='5521999999999', verbose_name='Telefone')
    email = models.EmailField(default='', verbose_name='E-mail')
    role_in_group = models.CharField(max_length=255, choices=ROLE_CHOICES, default='rotina', verbose_name='Cargo no grupo')
    admission_date = models.DateField(default='1970-01-01', verbose_name='Data de Admissão')
    responsible_hours = models.CharField(max_length=50, default='N/A', verbose_name='Horário Responsável')

    class Meta:
        verbose_name = "Anestesista"
        verbose_name_plural = "Anestesista"

    def clean(self):
        # Ensure the linked user has the correct user_type
        if self.user and self.user.user_type != ANESTESISTA_USER:
            raise ValidationError({
                'user': _('O usuário selecionado não é um Anestesista.')
            })

    def save(self, *args, **kwargs):
        # Call the clean method to ensure validation is done before saving
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Surgeon(models.Model):
    name = models.CharField(max_length=255, default='', verbose_name='Nome')
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    specialty = models.CharField(max_length=255, default='Cirurgião Geral', verbose_name='Especialidade')
    crm = models.CharField(max_length=20, unique=True, default='', verbose_name='CRM')
    phone = models.CharField(max_length=15, default='0000000000', verbose_name='Telefone')
    notes = models.TextField(blank=True, default='No notes', verbose_name='Notas (Sugestões de anestesia)')

    class Meta:
        verbose_name = "Cirurgião"
        verbose_name_plural = "Cirurgiões"

    def __str__(self):
        return self.name

class HospitalClinic(models.Model):
    name = models.CharField(max_length=255, default='', verbose_name='Nome')
    group = models.ForeignKey(Groups, on_delete=models.SET_NULL, verbose_name='Grupo', null=True, blank=True)
    address = models.CharField(max_length=255, default='No address provided', verbose_name='Endereço')
    surgery_center_phone = models.CharField(max_length=15, default='0000000000', verbose_name='Telefone do Centro Cirúrgico')
    hospital_phone = models.CharField(max_length=15, default='0000000000', verbose_name='Telefone do Hospital')

    class Meta:
        verbose_name = "Hospital / Clínica"
        verbose_name_plural = "Hospitais / Clínicas"

    def __str__(self):
        return self.name