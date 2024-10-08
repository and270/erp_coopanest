# Generated by Django 5.0.7 on 2024-09-06 00:58

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0004_procedimento_data_horario_fim'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='procedimento',
            name='contato_pacinete',
        ),
        migrations.AddField(
            model_name='procedimento',
            name='email_paciente',
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name='Email do Paciente'),
        ),
        migrations.AddField(
            model_name='procedimento',
            name='telefone_paciente',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Telefone do Paciente'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='data_horario_fim',
            field=models.DateTimeField(default=datetime.datetime(2024, 9, 6, 20, 0, tzinfo=datetime.timezone.utc), verbose_name='Horário de Término'),
        ),
    ]
