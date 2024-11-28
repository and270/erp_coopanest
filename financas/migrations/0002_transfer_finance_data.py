from django.db import migrations

def transfer_finance_data(apps, schema_editor):
    Procedimento = apps.get_model('agenda', 'Procedimento')
    ProcedimentoFinancas = apps.get_model('financas', 'ProcedimentoFinancas')
    
    for proc in Procedimento.objects.all():
        # Only create if there's any financial data to transfer
        if any([
            proc.tipo_cobranca,
            proc.valor_cobranca,
            proc.tipo_pagamento_direto,
        ]):
            ProcedimentoFinancas.objects.create(
                procedimento=proc,
                tipo_cobranca=proc.tipo_cobranca,
                valor_cobranca=proc.valor_cobranca,
                tipo_pagamento_direto=proc.tipo_pagamento_direto,
            )

def reverse_finance_data(apps, schema_editor):
    ProcedimentoFinancas = apps.get_model('financas', 'ProcedimentoFinancas')
    ProcedimentoFinancas.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('financas', '0001_initial'),  # The initial migration created ProcedimentoFinancas model
        ('agenda', '0040_alter_escalaanestesiologista_hora_fim_and_more'),  # Last agenda migration before this change
    ]

    operations = [
        migrations.RunPython(transfer_finance_data, reverse_finance_data),
    ] 