# Generated by Django 5.0.7 on 2024-09-27 00:29

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0018_remove_procedimento_survey_response'),
    ]

    operations = [
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_fim',
            field=models.TimeField(default=datetime.datetime(2024, 9, 27, 17, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Fim do Turno'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_inicio',
            field=models.TimeField(default=datetime.datetime(2024, 9, 27, 8, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Início do Turno'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='data_horario_fim',
            field=models.DateTimeField(default=datetime.datetime(2024, 9, 27, 20, 0, tzinfo=datetime.timezone.utc), verbose_name='Previsão de Término'),
        ),
    ]