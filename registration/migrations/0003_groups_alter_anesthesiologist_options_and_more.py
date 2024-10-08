# Generated by Django 5.0.7 on 2024-08-29 20:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0002_alter_customuser_user_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='Groups',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Nome do Grupo')),
            ],
            options={
                'verbose_name': 'Grupo',
                'verbose_name_plural': 'Grupos',
            },
        ),
        migrations.AlterModelOptions(
            name='anesthesiologist',
            options={'verbose_name': 'Anestesista', 'verbose_name_plural': 'Anestesista'},
        ),
        migrations.AlterModelOptions(
            name='customuser',
            options={'verbose_name': 'Usuário', 'verbose_name_plural': 'Usuários'},
        ),
        migrations.AlterModelOptions(
            name='hospitalclinic',
            options={'verbose_name': 'Hospital / Clínica', 'verbose_name_plural': 'Hospitais / Clínicas'},
        ),
        migrations.AlterModelOptions(
            name='surgeon',
            options={'verbose_name': 'Cirurgião', 'verbose_name_plural': 'Cirurgiões'},
        ),
        migrations.AddField(
            model_name='customuser',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='registration.groups', verbose_name='Grupo'),
        ),
        migrations.AddField(
            model_name='hospitalclinic',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='registration.groups', verbose_name='Grupo'),
        ),
        migrations.AddField(
            model_name='surgeon',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='registration.groups', verbose_name='Grupo'),
        ),
    ]
