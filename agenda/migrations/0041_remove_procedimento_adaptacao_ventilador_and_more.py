# Generated by Django 5.0.7 on 2024-11-27 21:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0040_alter_escalaanestesiologista_hora_fim_and_more'),
        ('qualidade', '0005_transfer_quality_data'),
        ('financas', '0002_transfer_finance_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='procedimento',
            name='adaptacao_ventilador',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='adesao_checklist',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='adesao_profilaxia',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='atividade',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='choro',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='clareza_informacoes',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='comentario_adicional',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='comunicacao_disponibilidade',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='conformidade_diretrizes',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='conforto_seguranca',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='consolabilidade',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='consolabilidade_painad',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='csat_score',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='data_horario_fim_efetivo',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='data_horario_inicio_efetivo',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='dor_pos_operatoria',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='encaminhamento_uti',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='escala',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='eva_score',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='evento_adverso_evitavel',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='eventos_adversos_graves',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='eventos_adversos_graves_desc',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='expressao_facial',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='expressao_facial_painad',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='face',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='linguagem_corporal',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='movimentos_membros_superiores',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='pernas',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='ponv',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='reacao_alergica_grave',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='reacao_alergica_grave_desc',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='respiracao',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='satisfacao_geral',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='tipo_cobranca',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='tipo_pagamento_direto',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='uso_tecnicas_assepticas',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='valor_cobranca',
        ),
        migrations.RemoveField(
            model_name='procedimento',
            name='vocalizacao_negativa',
        ),
    ]