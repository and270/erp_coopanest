# Generated by Django 5.0.7 on 2024-10-31 18:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0035_procedimentodetalhes_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='procedimentodetalhes',
            name='name',
            field=models.CharField(max_length=500, unique=True),
        ),
    ]