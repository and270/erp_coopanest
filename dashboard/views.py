from django.shortcuts import render
from django.db.models import Avg, Count, Case, When, F, Q, Sum
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from financas.models import ProcedimentoFinancas
from qualidade.models import ProcedimentoQualidade
from agenda.models import ProcedimentoDetalhes, Procedimento
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models.functions import TruncMonth, TruncDate
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
    if not period_days:
        period_days = 180  # Default to 6 months if no period is selected

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
    try:
        period_days = int(period_days)
        start_date = timezone.now() - timedelta(days=period_days)
        queryset = queryset.filter(
            procedimento__data_horario__gte=start_date
        )
    except (ValueError, TypeError):
        # If period_days is invalid, default to 180 days
        period_days = 180
        start_date = timezone.now() - timedelta(days=period_days)
        queryset = queryset.filter(
            procedimento__data_horario__gte=start_date
        )

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

    # Get date range and determine if we're using daily or monthly view
    date_range, view_type = get_date_range(period_days)

    if view_type == 'daily':
        # Daily view processing
        date_map = {
            d: {
                'cooperativa': 0,
                'hospital': 0,
                'particular': 0
            } for d in date_range
        }

        daily_data = queryset.annotate(
            date=TruncDate('procedimento__data_horario')
        ).values('date', 'tipo_cobranca').annotate(
            total=Sum('valor_cobranca')
        ).order_by('date')

        for item in daily_data:
            if item['date'] in date_map:
                date_map[item['date']][item['tipo_cobranca']] = item['total'] or 0

        sorted_dates = sorted(date_map.keys())
        date_labels = [d.strftime("%d/%m") for d in sorted_dates]
        coopanest_values = [date_map[d]['cooperativa'] for d in sorted_dates]
        hospital_values = [date_map[d]['hospital'] for d in sorted_dates]
        direta_values = [date_map[d]['particular'] for d in sorted_dates]

        # Calculate daily tickets
        daily_tickets = []
        daily_revenues = []
        for d in sorted_dates:
            day_procedures = queryset.filter(
                procedimento__data_horario__date=d
            )
            day_total = day_procedures.aggregate(
                total=Sum('valor_cobranca')
            )['total'] or 0
            day_count = day_procedures.count()
            daily_tickets.append(
                float(round(day_total / day_count if day_count > 0 else 0, 2))
            )
            daily_revenues.append(float(round(day_total, 2)))

        month_labels = date_labels
        monthly_tickets = daily_tickets
        monthly_revenues = daily_revenues

    else:
        # Monthly view processing (keep existing monthly code)
        month_map = {}
        for m in date_range:
            month_map[m.strftime("%Y-%m")] = {
                'cooperativa': 0,
                'hospital': 0,
                'particular': 0
            }

        monthly_data = queryset.annotate(
            month=TruncMonth('procedimento__data_horario')
        ).filter(
            valor_cobranca__isnull=False,  # Add this to exclude null values
            status_pagamento__in=['pago', 'pendente']  # Only include relevant statuses
        ).values('month', 'tipo_cobranca').annotate(
            total=Sum('valor_cobranca')
        ).order_by('month')

        # Add debug logging to check the values
        print("Monthly Data:", monthly_data)

        for item in monthly_data:
            if item['month'] and item['tipo_cobranca']:
                month_key = item['month'].strftime("%Y-%m")
                if month_key in month_map:
                    if item['tipo_cobranca'] == 'cooperativa':
                        month_map[month_key]['cooperativa'] = float(item['total'] or 0)
                    elif item['tipo_cobranca'] == 'hospital':
                        month_map[month_key]['hospital'] = float(item['total'] or 0)
                    elif item['tipo_cobranca'] == 'particular':
                        month_map[month_key]['particular'] = float(item['total'] or 0)

        # Add debug logging
        print("Month map after processing:", month_map)

        sorted_months = sorted(date_range)
        # Dicionário de meses em português
        meses_pt = {
            'January': 'Janeiro', 'February': 'Fevereiro', 'March': 'Março',
            'April': 'Abril', 'May': 'Maio', 'June': 'Junho', 'July': 'Julho',
            'August': 'Agosto', 'September': 'Setembro', 'October': 'Outubro',
            'November': 'Novembro', 'December': 'Dezembro'
        }
        month_labels = [meses_pt[m.strftime("%B")] for m in sorted_months]
        coopanest_values = [month_map[m.strftime("%Y-%m")]['cooperativa'] for m in sorted_months]
        hospital_values = [month_map[m.strftime("%Y-%m")]['hospital'] for m in sorted_months]
        direta_values = [month_map[m.strftime("%Y-%m")]['particular'] for m in sorted_months]

        # Add more debug logging
        print("Final values:")
        print("Labels:", month_labels)
        print("Coopanest:", coopanest_values)
        print("Hospital:", hospital_values)
        print("Direta:", direta_values)

        # Calculate monthly tickets and revenues
        monthly_tickets = []
        monthly_revenues = []
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
            monthly_revenues.append(float(round(month_total, 2)))

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

    # Get selected graph type from request, default to 'ticket'
    selected_graph_type = request.GET.get('graph_type', 'ticket')

    if selected_graph_type == 'ticket':
        period_total = queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor'] or 0
    else:
        # Add detailed debugging for total calculation
        procedures = queryset.values(
            'id', 
            'valor_cobranca', 
            'tipo_cobranca',
            'procedimento__data_horario'
        ).order_by('procedimento__data_horario')
        
        total_sum = 0
        for proc in procedures:
            total_sum += proc['valor_cobranca'] or 0
        
        period_total = queryset.aggregate(total=Sum('valor_cobranca'))['total'] or 0

    # Calculate anestesista total based on graph type and selected anestesista
    anestesista_total = 0
    if selected_anestesista:
        anestesista_queryset = queryset.filter(procedimento__anestesistas_responsaveis=selected_anestesista)
        if selected_graph_type == 'ticket':
            anestesista_total = anestesista_queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor'] or 0
        else:
            anestesista_total = anestesista_queryset.aggregate(total=Sum('valor_cobranca'))['total'] or 0
    else:
        # When no anesthetist is selected, divide the period total by number of anesthetists
        num_anestesistas = anestesistas.count()
        if num_anestesistas > 0:
            anestesista_total = period_total / num_anestesistas

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
        'period_total': period_total,
        'anestesista_total': anestesista_total,
        'selected_graph_type': selected_graph_type,
    }

    return render(request, 'dashboard_financas.html', context)

def get_date_range(period_days):
    end_date = timezone.now()
    start_date = end_date - timedelta(days=period_days)
    
    if period_days <= 30:  # For 30 days or less, return daily range
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.date())
            current_date += timedelta(days=1)
        return dates, 'daily'
    else:  # For more than 30 days, return monthly range
        months = []
        current_date = start_date.replace(day=1)
        while current_date <= end_date:
            months.append(current_date)
            current_date += relativedelta(months=1)
        return months, 'monthly'