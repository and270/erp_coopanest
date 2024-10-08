# Generated by Django 5.0.7 on 2024-10-08 23:41

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0020_alter_escalaanestesiologista_hora_fim_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='procedimento',
            name='cpf_paciente',
            field=models.CharField(default='000.000.000-00', max_length=15, verbose_name='CPF do Paciente'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_fim',
            field=models.TimeField(default=datetime.datetime(2024, 10, 8, 17, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Fim do Turno'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_inicio',
            field=models.TimeField(default=datetime.datetime(2024, 10, 8, 8, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Início do Turno'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='data_horario_fim',
            field=models.DateTimeField(default=datetime.datetime(2024, 10, 8, 20, 0, tzinfo=datetime.timezone.utc), verbose_name='Previsão de Término'),
        ),
    ]
