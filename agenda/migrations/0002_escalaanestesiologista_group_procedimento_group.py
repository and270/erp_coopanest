# Generated by Django 5.0.7 on 2024-09-04 16:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0001_initial'),
        ('registration', '0004_anesthesiologist_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='escalaanestesiologista',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='registration.groups', verbose_name='Grupo'),
        ),
        migrations.AddField(
            model_name='procedimento',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='registration.groups', verbose_name='Grupo'),
        ),
    ]