# Generated by Django 5.0.7 on 2024-09-09 16:00

import datetime
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0006_alter_procedimento_cirurgiao'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='escalaanestesiologista',
            name='coringa',
        ),
        migrations.RemoveField(
            model_name='escalaanestesiologista',
            name='fixo',
        ),
        migrations.AddField(
            model_name='escalaanestesiologista',
            name='dias_da_semana',
            field=models.CharField(choices=[(1, 'Segunda-feira'), (2, 'Terça-feira'), (3, 'Quarta-feira'), (4, 'Quinta-feira'), (5, 'Sexta-feira'), (6, 'Sábado'), (7, 'Domingo')], default='1', max_length=20, verbose_name='Dias da Semana'),
        ),
        migrations.AddField(
            model_name='escalaanestesiologista',
            name='escala_type',
            field=models.CharField(choices=[('plantonista', 'Plantonista'), ('substituto', 'Substituto'), ('ferias', 'Férias/Licença')], default='plantonista', max_length=40, verbose_name='Tipo de Escala'),
        ),
        migrations.AddField(
            model_name='escalaanestesiologista',
            name='hora_fim',
            field=models.TimeField(default=datetime.datetime(2024, 9, 9, 17, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Fim'),
        ),
        migrations.AddField(
            model_name='escalaanestesiologista',
            name='hora_inicio',
            field=models.TimeField(default=datetime.datetime(2024, 9, 9, 8, 0, tzinfo=datetime.timezone.utc), verbose_name='Hora de Início'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='data_fim',
            field=models.DateField(default=django.utils.timezone.now, verbose_name='Fim do Turno'),
        ),
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='data_inicio',
            field=models.DateField(default=django.utils.timezone.now, verbose_name='Início do Turno'),
        ),
        migrations.AlterField(
            model_name='procedimento',
            name='data_horario_fim',
            field=models.DateTimeField(default=datetime.datetime(2024, 9, 9, 20, 0, tzinfo=datetime.timezone.utc), verbose_name='Horário de Término'),
        ),
    ]