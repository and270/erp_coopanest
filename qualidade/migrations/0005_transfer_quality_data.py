from django.db import migrations

def transfer_quality_data(apps, schema_editor):
    Procedimento = apps.get_model('agenda', 'Procedimento')
    ProcedimentoQualidade = apps.get_model('qualidade', 'ProcedimentoQualidade')
    
    for proc in Procedimento.objects.all():
        # Only create if there's any quality data to transfer
        if any([
            proc.data_horario_inicio_efetivo,
            proc.data_horario_fim_efetivo,
            proc.dor_pos_operatoria,
            proc.escala,
            proc.eva_score,
            proc.face,
            proc.pernas,
            proc.atividade,
            proc.choro,
            proc.consolabilidade,
            proc.expressao_facial,
            proc.movimentos_membros_superiores,
            proc.adaptacao_ventilador,
            proc.respiracao,
            proc.vocalizacao_negativa,
            proc.expressao_facial_painad,
            proc.linguagem_corporal,
            proc.consolabilidade_painad,
            proc.eventos_adversos_graves,
            proc.eventos_adversos_graves_desc,
            proc.reacao_alergica_grave,
            proc.reacao_alergica_grave_desc,
            proc.encaminhamento_uti,
            proc.evento_adverso_evitavel,
            proc.adesao_checklist,
            proc.uso_tecnicas_assepticas,
            proc.conformidade_diretrizes,
            proc.ponv,
            proc.adesao_profilaxia,
            proc.satisfacao_geral,
            proc.clareza_informacoes,
            proc.comunicacao_disponibilidade,
            proc.conforto_seguranca,
            proc.comentario_adicional,
            proc.csat_score,
        ]):
            ProcedimentoQualidade.objects.create(
                procedimento=proc,
                data_horario_inicio_efetivo=proc.data_horario_inicio_efetivo,
                data_horario_fim_efetivo=proc.data_horario_fim_efetivo,
                dor_pos_operatoria=proc.dor_pos_operatoria,
                escala=proc.escala,
                eva_score=proc.eva_score,
                face=proc.face,
                pernas=proc.pernas,
                atividade=proc.atividade,
                choro=proc.choro,
                consolabilidade=proc.consolabilidade,
                expressao_facial=proc.expressao_facial,
                movimentos_membros_superiores=proc.movimentos_membros_superiores,
                adaptacao_ventilador=proc.adaptacao_ventilador,
                respiracao=proc.respiracao,
                vocalizacao_negativa=proc.vocalizacao_negativa,
                expressao_facial_painad=proc.expressao_facial_painad,
                linguagem_corporal=proc.linguagem_corporal,
                consolabilidade_painad=proc.consolabilidade_painad,
                eventos_adversos_graves=proc.eventos_adversos_graves,
                eventos_adversos_graves_desc=proc.eventos_adversos_graves_desc,
                reacao_alergica_grave=proc.reacao_alergica_grave,
                reacao_alergica_grave_desc=proc.reacao_alergica_grave_desc,
                encaminhamento_uti=proc.encaminhamento_uti,
                evento_adverso_evitavel=proc.evento_adverso_evitavel,
                adesao_checklist=proc.adesao_checklist,
                uso_tecnicas_assepticas=proc.uso_tecnicas_assepticas,
                conformidade_diretrizes=proc.conformidade_diretrizes,
                ponv=proc.ponv,
                adesao_profilaxia=proc.adesao_profilaxia,
                satisfacao_geral=proc.satisfacao_geral,
                clareza_informacoes=proc.clareza_informacoes,
                comunicacao_disponibilidade=proc.comunicacao_disponibilidade,
                conforto_seguranca=proc.conforto_seguranca,
                comentario_adicional=proc.comentario_adicional,
                csat_score=proc.csat_score,
            )

def reverse_quality_data(apps, schema_editor):
    ProcedimentoQualidade = apps.get_model('qualidade', 'ProcedimentoQualidade')
    ProcedimentoQualidade.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('qualidade', '0004_procedimentoqualidade'),  # The migration that created ProcedimentoQualidade model
        ('agenda', '0040_alter_escalaanestesiologista_hora_fim_and_more'),  # Last agenda migration before this change
    ]

    operations = [
        migrations.RunPython(transfer_quality_data, reverse_quality_data),
    ] 