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
from django.http import HttpResponse
import xlsxwriter
from io import BytesIO
from qualidade.models import AvaliacaoRPA

@login_required
@login_required
def dashboard_view(request):
    """Dashboard de Qualidade, com opção de Período Personalizado."""
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    user_group = request.user.group
    
    # Get 'period' from URL; can be an integer (days) or 'custom'
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    procedimento = request.GET.get('procedimento')

    # Get view preferences
    dor_view = request.GET.get('dor_view', 'final')     # 'final' or 'rpa'
    ponv_view = request.GET.get('ponv_view', 'final')   # 'final' or 'rpa'
    evento_view = request.GET.get('evento_view', 'final')  # 'final' or 'rpa'

    # Base querysets
    queryset = ProcedimentoQualidade.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(
        procedimento__status='finished',
        procedimento__group=user_group
    )
    rpa_queryset = AvaliacaoRPA.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(
        procedimento__status='finished',
        procedimento__group=user_group
    )

    # Optional filter by procedimento (name)
    if procedimento:
        queryset = queryset.filter(procedimento__procedimento_principal__name=procedimento)
        rpa_queryset = rpa_queryset.filter(procedimento__procedimento_principal__name=procedimento)

    # -----------------------------------------------------------------------
    # 1) Handle custom date range if 'period=custom' + both start/end are given
    # -----------------------------------------------------------------------
    delta_days = 0  # we will calculate how many days in the date range
    if period == 'custom' and start_date_str and end_date_str:
        try:
            custom_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            custom_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            if custom_start > custom_end:
                # if user picks reversed dates, swap them
                custom_start, custom_end = custom_end, custom_start
            
            # Filter by custom range (inclusive)
            queryset = queryset.filter(
                procedimento__data_horario__date__gte=custom_start.date(),
                procedimento__data_horario__date__lte=custom_end.date()
            )
            rpa_queryset = rpa_queryset.filter(
                procedimento__data_horario__date__gte=custom_start.date(),
                procedimento__data_horario__date__lte=custom_end.date()
            )

            # Calculate how many days in that range
            delta_days = (custom_end.date() - custom_start.date()).days
            selected_period = 'custom'

        except ValueError:
            # If there's an error parsing dates, fallback to 180 days
            selected_period = 180
            start_date = timezone.now() - timedelta(days=180)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            rpa_queryset = rpa_queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = 180
    else:
        # -------------------------------------------------------------------
        # 2) If not custom, interpret 'period' as integer days
        # -------------------------------------------------------------------
        if not period:
            period = 180  # fallback
        try:
            period_days = int(period)
            selected_period = period_days
            start_date = timezone.now() - timedelta(days=period_days)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            rpa_queryset = rpa_queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = period_days
        except (ValueError, TypeError):
            # if invalid, fallback
            selected_period = 180
            start_date = timezone.now() - timedelta(days=180)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            rpa_queryset = rpa_queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = 180

    # Now proceed with the rest of the metrics
    total_count = queryset.count()
    rpa_total_count = rpa_queryset.count()

    # Dor pos-operatoria
    dor_count = (rpa_queryset.filter(dor_pos_operatoria=True).count() if dor_view == 'rpa' 
                 else queryset.filter(dor_pos_operatoria=True).count())
    dor_total = rpa_total_count if dor_view == 'rpa' else total_count

    # PONV
    ponv_count = (rpa_queryset.filter(ponv=True).count() if ponv_view == 'rpa' 
                  else queryset.filter(ponv=True).count())
    ponv_total = rpa_total_count if ponv_view == 'rpa' else total_count

    # Evento Adverso
    evento_count = (rpa_queryset.filter(evento_adverso=True).count() if evento_view == 'rpa' 
                    else queryset.filter(evento_adverso_evitavel=True).count())
    evento_total = rpa_total_count if evento_view == 'rpa' else total_count

    # Atraso médio
    avg_delay = queryset.aggregate(
        avg_delay=Avg(F('data_horario_inicio_efetivo') - F('procedimento__data_horario'))
    )['avg_delay']

    # Monta o dicionário de métricas
    metrics = {
        'eventos_adversos': queryset.filter(eventos_adversos_graves=True).count() / total_count * 100 if total_count > 0 else None,
        'atraso_medio': (
            f"{avg_delay.days} dias, {int((avg_delay.seconds // 3600)):02d}:{int((avg_delay.seconds % 3600) // 60):02d}"
            if avg_delay and avg_delay.days > 0 
            else f"{int(avg_delay.seconds // 3600):02d}:{int((avg_delay.seconds % 3600) // 60):02d}" 
            if avg_delay else None
        ),
        'duracao_media': str(queryset.aggregate(
            avg_duration=Avg(F('data_horario_fim_efetivo') - F('data_horario_inicio_efetivo'))
        )['avg_duration']).split('.')[0].rsplit(':', 1)[0] if total_count > 0 else None,
        'reacoes_alergicas': queryset.filter(reacao_alergica_grave=True).count() / total_count * 100 if total_count > 0 else None,
        'encaminhamentos_uti': queryset.filter(encaminhamento_uti=True).count() / total_count * 100 if total_count > 0 else None,
        'ponv': (ponv_count / ponv_total * 100) if ponv_total > 0 else None,
        'dor_pos_operatoria': (dor_count / dor_total * 100) if dor_total > 0 else None,
        'evento_adverso_evitavel': (evento_count / evento_total * 100) if evento_total > 0 else None,
        'adesao_checklist': queryset.filter(adesao_checklist=True).count() / total_count * 100 if total_count > 0 else None,
        'conformidade_protocolos': queryset.filter(conformidade_diretrizes=True).count() / total_count * 100 if total_count > 0 else None,
        'tecnicas_assepticas': queryset.filter(uso_tecnicas_assepticas=True).count() / total_count * 100 if total_count > 0 else None,
        'csat_score': queryset.aggregate(Avg('csat_score'))['csat_score__avg'],
        'ponv_view': ponv_view,
        'evento_view': evento_view,
        'dor_view': dor_view,
    }

    # Procedures for the filter
    procedimentos = ProcedimentoDetalhes.objects.filter(
        procedimento__group=user_group
    ).order_by('name').distinct()

    return render(request, 'dashboard.html', {
        'metrics': metrics,
        'procedimentos': procedimentos,
        'selected_procedimento': procedimento,
        'selected_period': selected_period,  # can be int or 'custom'
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def financas_dashboard_view(request):
    """Dashboard de Finanças, com opção de Período Personalizado."""
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    user_group = request.user.group

    # Similar approach for handling custom or numeric period
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    queryset = (
        ProcedimentoFinancas.objects
        .select_related('procedimento', 'procedimento__procedimento_principal')
        .filter(procedimento__group=user_group)
    )

    # Filter by anestesista if given
    selected_anestesista = request.GET.get('anestesista')
    if selected_anestesista:
        queryset = queryset.filter(procedimento__anestesistas_responsaveis=selected_anestesista)

    # Filter by procedimento if given
    procedimento = request.GET.get('procedimento')
    if procedimento:
        queryset = queryset.filter(procedimento__procedimento_principal__name=procedimento)

    # -----------------------------------------------------------------------
    # Handle period - either custom or numeric
    # -----------------------------------------------------------------------
    delta_days = 0
    if period == 'custom' and start_date_str and end_date_str:
        try:
            custom_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            custom_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            if custom_start > custom_end:
                custom_start, custom_end = custom_end, custom_start
            queryset = queryset.filter(
                procedimento__data_horario__date__gte=custom_start.date(),
                procedimento__data_horario__date__lte=custom_end.date()
            )
            delta_days = (custom_end.date() - custom_start.date()).days
            selected_period = 'custom'
        except ValueError:
            # fallback
            selected_period = 180
            start_date = timezone.now() - timedelta(days=180)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = 180
    else:
        if not period:
            period = 180
        try:
            period_days = int(period)
            selected_period = period_days
            start_date = timezone.now() - timedelta(days=period_days)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = period_days
        except (ValueError, TypeError):
            selected_period = 180
            start_date = timezone.now() - timedelta(days=180)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            delta_days = 180

    # -----------------------------------------------------------------------
    # Now that we have filtered by period, proceed with existing finances logic
    # -----------------------------------------------------------------------
    total_count = queryset.count()

    # Anestesias: how many distinct procedures
    anestesias_count = queryset.values('procedimento').distinct().count()

    # Sum by status_pagamento
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

    # Percent helper
    def percentage(part, whole):
        if whole > 0:
            return (float(part) / float(whole)) * 100
        return 0

    pago_pct = percentage(valor_pago, total_valor)
    pendente_pct = percentage(valor_pendente, total_valor)
    glosa_pct = percentage(valor_glosa, total_valor)

    # Tempo Médio de Recebimento
    paid_procedures = queryset.filter(
        status_pagamento='pago',
        data_pagamento__isnull=False,
        procedimento__data_horario__isnull=False
    )
    avg_recebimento = None
    if paid_procedures.exists():
        avg_diff = paid_procedures.annotate(
            diff=F('data_pagamento') - F('procedimento__data_horario')
        ).aggregate(Avg('diff'))['diff__avg']
        if avg_diff:
            avg_days = avg_diff.days
            if avg_days >= 30:
                avg_months = avg_days // 30  # approximate
                avg_recebimento = f"{avg_months} meses"
            else:
                avg_recebimento = f"{avg_days} dias"

    # Ticket Médio (average valor_cobranca)
    avg_ticket = queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor']

    # Decide daily vs monthly for charting
    date_range, view_type = get_date_range(delta_days)

    # Depending on daily or monthly, we gather data for charts
    if view_type == 'daily':
        # Prepare a daily map
        date_map = {
            d: {'cooperativa': 0, 'hospital': 0, 'particular': 0}
            for d in date_range
        }

        daily_data = queryset.annotate(
            date=TruncDate('procedimento__data_horario')
        ).filter(
            valor_cobranca__isnull=False,
            status_pagamento__in=['pago', 'pendente']
        ).values('date', 'tipo_cobranca').annotate(
            total=Sum('valor_cobranca')
        ).order_by('date')

        for item in daily_data:
            if item['date'] in date_map and item['tipo_cobranca']:
                tipo = item['tipo_cobranca']
                if tipo in ['cooperativa', 'hospital', 'particular']:
                    date_map[item['date']][tipo] = float(item['total'] or 0)

        sorted_dates = sorted(date_map.keys())
        date_labels = [d.strftime("%d/%m") for d in sorted_dates]
        coopanest_values = [date_map[d]['cooperativa'] for d in sorted_dates]
        hospital_values = [date_map[d]['hospital'] for d in sorted_dates]
        direta_values = [date_map[d]['particular'] for d in sorted_dates]

        # Calculate daily tickets
        daily_tickets = []
        daily_revenues = []
        for d in sorted_dates:
            day_procedures = queryset.filter(procedimento__data_horario__date=d)
            day_total = day_procedures.aggregate(total=Sum('valor_cobranca'))['total'] or 0
            day_count = day_procedures.count()
            daily_tickets.append(
                float(round(day_total / day_count if day_count > 0 else 0, 2))
            )
            daily_revenues.append(float(round(day_total, 2)))

        month_labels = date_labels
        monthly_tickets = daily_tickets
        monthly_revenues = daily_revenues

    else:
        # Monthly logic
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
            valor_cobranca__isnull=False,
            status_pagamento__in=['pago', 'pendente']
        ).values('month', 'tipo_cobranca').annotate(
            total=Sum('valor_cobranca')
        ).order_by('month')

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

        sorted_months = sorted(date_range)
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

        # monthly tickets & revenues
        monthly_tickets = []
        monthly_revenues = []
        for m in sorted_months:
            month_procedures = queryset.filter(
                procedimento__data_horario__year=m.year,
                procedimento__data_horario__month=m.month
            )
            month_total = month_procedures.aggregate(total=Sum('valor_cobranca'))['total'] or 0
            month_count = month_procedures.count()
            monthly_tickets.append(float(round(month_total / month_count if month_count > 0 else 0, 2)))
            monthly_revenues.append(float(round(month_total, 2)))

    # For the pie chart
    total_coopanest = sum(coopanest_values)
    total_hospital = sum(hospital_values)
    total_direta = sum(direta_values)
    total_all = total_coopanest + total_hospital + total_direta

    coopanest_pct = (total_coopanest / total_all * 100) if total_all > 0 else 0
    hospital_pct = (total_hospital / total_all * 100) if total_all > 0 else 0
    direta_pct = (total_direta / total_all * 100) if total_all > 0 else 0

    # Procedures for filter
    procedimentos = ProcedimentoDetalhes.objects.filter(
        procedimento__group=user_group
    ).order_by('name').distinct()

    # Anestesistas for filter
    anestesistas = Anesthesiologist.objects.filter(
        group=user_group
    ).order_by('name')

    selected_graph_type = request.GET.get('graph_type', 'ticket')
    if selected_graph_type == 'ticket':
        period_total = queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor'] or 0
    else:
        period_total = queryset.aggregate(total=Sum('valor_cobranca'))['total'] or 0

    anestesista_total = 0
    if selected_anestesista:
        anestesista_queryset = queryset.filter(procedimento__anestesistas_responsaveis=selected_anestesista)
        if selected_graph_type == 'ticket':
            anestesista_total = anestesista_queryset.aggregate(avg_valor=Avg('valor_cobranca'))['avg_valor'] or 0
        else:
            anestesista_total = anestesista_queryset.aggregate(total=Sum('valor_cobranca'))['total'] or 0
    else:
        num_anestesistas = anestesistas.count()
        if num_anestesistas > 0:
            anestesista_total = period_total / num_anestesistas

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
        'selected_period': selected_period,  # could be int or 'custom'
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
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

@login_required
def export_financas_excel(request):
    """Handle Excel export for financial dashboard data"""
    if not request.user.validado:
        return HttpResponse('Unauthorized', status=401)

    # Create output buffer
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Dashboard Financeiro')

    # Add formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#0D6EFD',
        'color': 'white',
        'align': 'center',
        'valign': 'vcenter'
    })
    currency_format = workbook.add_format({'num_format': 'R$ #,##0.00'})
    percent_format = workbook.add_format({'num_format': '0.00%'})

    # Get the same data as in the dashboard view
    user_group = request.user.group
    period_days = request.GET.get('period', 180)
    selected_anestesista = request.GET.get('anestesista')
    procedimento = request.GET.get('procedimento')

    queryset = ProcedimentoFinancas.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(procedimento__group=user_group)

    # Apply filters
    if selected_anestesista:
        queryset = queryset.filter(procedimento__anestesistas_responsaveis=selected_anestesista)
    if procedimento:
        queryset = queryset.filter(procedimento__procedimento_principal__name=procedimento)
    
    try:
        period_days = int(period_days)
        start_date = timezone.now() - timedelta(days=period_days)
        queryset = queryset.filter(procedimento__data_horario__gte=start_date)
    except (ValueError, TypeError):
        period_days = 180
        start_date = timezone.now() - timedelta(days=period_days)
        queryset = queryset.filter(procedimento__data_horario__gte=start_date)

    # Write headers
    headers = [
        'Data', 'Procedimento', 'Anestesista', 'Tipo de Cobrança',
        'Valor', 'Status', 'Data de Pagamento'
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Write data
    row = 1
    for item in queryset:
        worksheet.write(row, 0, item.procedimento.data_horario.strftime('%d/%m/%Y'))
        worksheet.write(row, 1, item.procedimento.procedimento_principal.name if item.procedimento.procedimento_principal else '')
        worksheet.write(row, 2, ', '.join([a.name for a in item.procedimento.anestesistas_responsaveis.all()]))
        worksheet.write(row, 3, item.tipo_cobranca)
        worksheet.write(row, 4, float(item.valor_cobranca or 0), currency_format)
        worksheet.write(row, 5, item.status_pagamento)
        worksheet.write(row, 6, item.data_pagamento.strftime('%d/%m/%Y') if item.data_pagamento else '')
        row += 1

    # Add summary sheet
    summary = workbook.add_worksheet('Resumo')
    
    # Write summary headers
    summary_headers = ['Métrica', 'Valor']
    for col, header in enumerate(summary_headers):
        summary.write(0, col, header, header_format)

    # Calculate summary data
    total_count = queryset.count()
    total_valor = queryset.aggregate(total=Sum('valor_cobranca'))['total'] or 0
    valor_pago = queryset.filter(status_pagamento='pago').aggregate(total=Sum('valor_cobranca'))['total'] or 0
    valor_pendente = queryset.filter(status_pagamento='pendente').aggregate(total=Sum('valor_cobranca'))['total'] or 0
    valor_glosa = queryset.filter(status_pagamento='glosa').aggregate(total=Sum('valor_cobranca'))['total'] or 0

    # Write summary data
    summary_data = [
        ('Total de Anestesias', total_count),
        ('Valor Total', total_valor),
        ('Valor Pago', valor_pago),
        ('Valor Pendente', valor_pendente),
        ('Valor em Glosa', valor_glosa),
        ('% Pago', valor_pago/total_valor if total_valor else 0),
        ('% Pendente', valor_pendente/total_valor if total_valor else 0),
        ('% Glosa', valor_glosa/total_valor if total_valor else 0),
    ]

    for i, (label, value) in enumerate(summary_data, 1):
        summary.write(i, 0, label)
        if isinstance(value, (int, float)):
            if 'Valor' in label:
                summary.write(i, 1, value, currency_format)
            elif '%' in label:
                summary.write(i, 1, value, percent_format)
            else:
                summary.write(i, 1, value)

    # Adjust column widths
    for sheet in [worksheet, summary]:
        for i, width in enumerate([15, 30, 30, 15, 15, 15, 15]):
            sheet.set_column(i, i, width)

    workbook.close()
    
    # Create the HttpResponse
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=dashboard_financas.xlsx'
    
    return response

def get_date_range(period_days):
    """
    Existing helper function that returns:
      - a list of date objects (daily or monthly) based on 'period_days'
      - a string: 'daily' or 'monthly'
    """
    end_date = timezone.now()
    start_date = end_date - timedelta(days=period_days)
    
    if period_days <= 30:  # For 30 days or less, daily
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.date())
            current_date += timedelta(days=1)
        return dates, 'daily'
    else:
        # For more than 30 days, monthly
        months = []
        current_date = start_date.replace(day=1)
        while current_date <= end_date:
            months.append(current_date)
            current_date += relativedelta(months=1)
        return months, 'monthly'