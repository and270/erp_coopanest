# Generated by Django 5.0.7 on 2024-10-31 03:26

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0033_alter_procedimento_procedimento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_fim',
            field=models.TimeField(default=datetime.datetime(2024, 10, 31, 17, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Fim do Turno'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='hora_inicio',
            field=models.TimeField(default=datetime.datetime(2024, 10, 31, 8, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Início do Turno'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='data_horario_fim',
            field=models.DateTimeField(default=datetime.datetime(2024, 10, 31, 20, 0, tzinfo=datetime.timezone.utc), verbose_name='Previsão de Término'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='valor_cobranca',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Valor'),
        ),
    ]