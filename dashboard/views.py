from django.shortcuts import render
from django.db.models import Avg, Count, Case, When, F, Q, Sum
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from financas.models import ProcedimentoFinancas
from qualidade.models import ProcedimentoQualidade
from agenda.models import ProcedimentoDetalhes, Procedimento
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models.functions import TruncMonth
from registration.models import Anesthesiologist
from dateutil.relativedelta import relativedelta

@login_required
def dashboard_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    user_group = request.user.group
    
    procedimento = request.GET.get('procedimento')
    
    # Base queryset with proper joins and group filter
    queryset = ProcedimentoQualidade.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(
        procedimento__status='finished',
        procedimento__group=user_group
    )
    
    if procedimento:
        queryset = queryset.filter(
            procedimento__procedimento_principal__name=procedimento
        )

    # Get period filter
    period_days = request.GET.get('period')  # Remove default value
    if period_days:
        try:
            period_days = int(period_days)
            start_date = timezone.now() - timedelta(days=period_days)
            queryset = queryset.filter(
                procedimento__data_horario__gte=start_date
            )
        except ValueError:
            pass  # Invalid period parameter, ignore filter

    total_count = queryset.count()
    avg_delay = queryset.aggregate(
        avg_delay=Avg(F('data_horario_inicio_efetivo') - F('procedimento__data_horario'))
    )['avg_delay']

    metrics = {
        'eventos_adversos': queryset.filter(eventos_adversos_graves=True).count() / total_count * 100 if total_count > 0 else None,
        'atraso_medio': (f"{avg_delay.days} dias, {int((avg_delay.seconds // 3600)):02d}:{int((avg_delay.seconds % 3600) // 60):02d}" 
                        if avg_delay and avg_delay.days > 0 
                        else f"{int(avg_delay.seconds // 3600):02d}:{int((avg_delay.seconds % 3600) // 60):02d}" if avg_delay 
                        else None),
        'duracao_media': str(queryset.aggregate(
            avg_duration=Avg(F('data_horario_fim_efetivo') - F('data_horario_inicio_efetivo'))
        )['avg_duration']).split('.')[0].rsplit(':', 1)[0] if total_count > 0 else None,
        'reacoes_alergicas': queryset.filter(reacao_alergica_grave=True).count() / total_count * 100 if total_count > 0 else None,
        'encaminhamentos_uti': queryset.filter(encaminhamento_uti=True).count() / total_count * 100 if total_count > 0 else None,
        'ponv': queryset.filter(ponv=True).count() / total_count * 100 if total_count > 0 else None,
        'dor_pos_operatoria': queryset.filter(dor_pos_operatoria=True).count() / total_count * 100 if total_count > 0 else None,
        'evento_adverso_evitavel': queryset.filter(evento_adverso_evitavel=True).count() / total_count * 100 if total_count > 0 else None,
        'adesao_checklist': queryset.filter(adesao_checklist=True).count() / total_count * 100 if total_count > 0 else None,
        'conformidade_protocolos': queryset.filter(conformidade_diretrizes=True).count() / total_count * 100 if total_count > 0 else None,
        'tecnicas_assepticas': queryset.filter(uso_tecnicas_assepticas=True).count() / total_count * 100 if total_count > 0 else None,
        'csat_score': queryset.aggregate(Avg('csat_score'))['csat_score__avg'],
    }

    # Get procedure types for filter (only from the same group)
    procedimentos = ProcedimentoDetalhes.objects.filter(
        procedimento__group=user_group
    ).order_by('name').distinct()

    print(f"duracao_media: {metrics['duracao_media']}")
    return render(request, 'dashboard.html', {
        'metrics': metrics,
        'procedimentos': procedimentos,
        'selected_procedimento': procedimento,
        'selected_period': period_days,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def financas_dashboard_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    user_group = request.user.group

    # Period filter
    period_days = request.GET.get('period')
    queryset = ProcedimentoFinancas.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(
        procedimento__group=user_group
    )

    # Get selected anestesista - Move this up before any calculations
    selected_anestesista = request.GET.get('anestesista')
    if selected_anestesista:
        queryset = queryset.filter(
            procedimento__anestesistas_responsaveis=selected_anestesista
        )

    # Get procedure filter and apply it
    procedimento = request.GET.get('procedimento')
    if procedimento:
        queryset = queryset.filter(
            procedimento__procedimento_principal__name=procedimento
        )

    # Apply period filter
    if period_days:
        try:
            period_days = int(period_days)
            start_date = timezone.now() - timedelta(days=period_days)
            queryset = queryset.filter(
                procedimento__data_horario__gte=start_date
            )
        except ValueError:
            pass

    # Default period: last 6 months if no filter
    if not period_days:
        start_date = timezone.now() - timedelta(days=180)
        queryset = queryset.filter(procedimento__data_horario__gte=start_date)

    # Add some debug prints to verify the filtering
    print(f"Selected anestesista: {selected_anestesista}")
    print(f"Total procedures after filtering: {queryset.count()}")
    if selected_anestesista:
        print(f"Procedures for selected anestesista: {queryset.values_list('procedimento__id', flat=True)}")

    total_count = queryset.count()

    # Anestesias: Count how many procedures had anesthesiologists in the last 6 months
    anestesias_count = queryset.filter(
        procedimento__anestesistas_responsaveis__isnull=False
    ).distinct().count()

    # Valores Totais por Status
    totals_by_status = queryset.values('status_pagamento').annotate(
        total=Sum('valor_cobranca')
    )

    total_valor = sum(item['total'] for item in totals_by_status if item['total'] is not None) if totals_by_status else 0

    def get_status_value(status):
        for item in totals_by_status:
            if item['status_pagamento'] == status and item['total']:
                return item['total']
        return 0

    valor_pago = get_status_value('pago')
    valor_pendente = get_status_value('pendente')
    valor_glosa = get_status_value('glosa')

    # Compute percentages
    def percentage(part, whole):
        if whole and whole > 0:
            return (float(part) / float(whole)) * 100
        return 0

    pago_pct = percentage(valor_pago, total_valor)
    pendente_pct = percentage(valor_pendente, total_valor)
    glosa_pct = percentage(valor_glosa, total_valor)

    # Tempo Médio de Recebimento (for paid procedures only)
    paid_procedures = queryset.filter(status_pagamento='pago', data_pagamento__isnull=False, procedimento__data_horario__isnull=False)
    avg_recebimento = None
    if paid_procedures.exists():
        avg_diff = paid_procedures.annotate(
            diff=F('data_pagamento') - F('procedimento__data_horario')
        ).aggregate(Avg('diff'))['diff__avg']
        if avg_diff:
            # avg_diff is a timedelta
            # Convert to months approximation or just days
            # Let's say we present it in months:
            avg_days = avg_diff.days
            avg_months = avg_days // 30  # rough approximation
            avg_recebimento = f"{avg_months} meses" if avg_months > 0 else f"{avg_days} dias"

    # Ticket Médio (average valor_cobranca)
    avg_ticket = queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor']

    # Get monthly data for charts
    if period_days:
        try:
            period_days = int(period_days)
        except ValueError:
            period_days = 180  # Default to 6 months if invalid
    else:
        period_days = 180  # Default period

    # Get all months in the range
    all_months = get_month_range(period_days)

    # Initialize the month_map with all months and zero values
    month_map = {
        m: {
            'cooperativa': 0,
            'hospital': 0,
            'particular': 0
        } for m in all_months
    }

    # Get monthly data from database
    monthly_data = queryset.annotate(
        month=TruncMonth('procedimento__data_horario')
    ).values('month', 'tipo_cobranca').annotate(
        total=Sum('valor_cobranca')
    ).order_by('month')

    # Fill in actual values where they exist
    for item in monthly_data:
        m = item['month'].replace(day=1)  # Normalize to first day of month
        if m in month_map:
            month_map[m][item['tipo_cobranca']] = item['total'] or 0

    # Sort months and prepare data for charts
    sorted_months = sorted(month_map.keys())
    month_labels = [m.strftime("%B") for m in sorted_months]
    coopanest_values = [month_map[m]['cooperativa'] for m in sorted_months]
    hospital_values = [month_map[m]['hospital'] for m in sorted_months]
    direta_values = [month_map[m]['particular'] for m in sorted_months]

    # Calculate monthly tickets with zero handling
    monthly_tickets = []
    for m in sorted_months:
        month_procedures = queryset.filter(
            procedimento__data_horario__year=m.year,
            procedimento__data_horario__month=m.month
        )
        month_total = month_procedures.aggregate(
            total=Sum('valor_cobranca')
        )['total'] or 0
        month_count = month_procedures.count()
        monthly_tickets.append(
            float(round(month_total / month_count if month_count > 0 else 0, 2))
        )

    # Calculate monthly revenues
    monthly_revenues = []
    for m in sorted_months:
        month_total = queryset.filter(
            procedimento__data_horario__year=m.year,
            procedimento__data_horario__month=m.month
        ).aggregate(
            total=Sum('valor_cobranca')
        )['total'] or 0
        monthly_revenues.append(float(round(month_total, 2)))

    # Add some debug prints
    print(f"monthly_tickets: {monthly_tickets}")
    print(f"monthly_revenues: {monthly_revenues}")

    # Calculate percentages for the pie chart
    total_coopanest = sum(coopanest_values)
    total_hospital = sum(hospital_values)
    total_direta = sum(direta_values)
    total_all = total_coopanest + total_hospital + total_direta

    coopanest_pct = (total_coopanest / total_all * 100) if total_all > 0 else 0
    hospital_pct = (total_hospital / total_all * 100) if total_all > 0 else 0
    direta_pct = (total_direta / total_all * 100) if total_all > 0 else 0

    # Get procedure types for filter (only from the same group)
    procedimentos = ProcedimentoDetalhes.objects.filter(
        procedimento__group=user_group
    ).order_by('name').distinct()

    # Get anestesistas for filter (using the correct model)
    anestesistas = Anesthesiologist.objects.filter(
        group=user_group
    ).order_by('name')

    # Return to template
    context = {
        'anestesias_count': anestesias_count,
        'valor_pago': valor_pago,
        'valor_pendente': valor_pendente,
        'valor_glosa': valor_glosa,
        'pago_pct': pago_pct,
        'pendente_pct': pendente_pct,
        'glosa_pct': glosa_pct,
        'avg_recebimento': avg_recebimento,
        'avg_ticket': avg_ticket,
        'months': month_labels,
        'coopanest_values': coopanest_values,
        'hospital_values': hospital_values,
        'direta_values': direta_values,
        'selected_period': period_days,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'monthly_tickets': monthly_tickets,
        'coopanest_pct': coopanest_pct,
        'hospital_pct': hospital_pct,
        'direta_pct': direta_pct,
        'procedimentos': procedimentos,
        'selected_procedimento': procedimento,
        'anestesistas': anestesistas,
        'selected_anestesista': selected_anestesista,
        'monthly_revenues': monthly_revenues,
    }

    return render(request, 'dashboard_financas.html', context)

def get_month_range(period_days):
    end_date = timezone.now()
    start_date = end_date - timedelta(days=period_days)
    
    # Generate all months in the range
    months = []
    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        months.append(current_date)
        current_date += relativedelta(months=1)
    
    return months