# Generated by Django 5.0.7 on 2024-09-11 18:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0008_alter_escalaanestesiologista_data_fim_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='escalaanestesiologista',
            name='dias_da_semana',
            field=models.CharField(choices=[('1', 'Segunda-feira'), ('2', 'Terça-feira'), ('3', 'Quarta-feira'), ('4', 'Quinta-feira'), ('5', 'Sexta-feira'), ('6', 'Sábado'), ('0', 'Domingo')], default='1', max_length=20, verbose_name='Dias da Semana'),
        ),
    ]
