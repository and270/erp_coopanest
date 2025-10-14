from django.shortcuts import render
from django.db.models import Avg, Count, Case, When, F, Q, Sum, ExpressionWrapper, DurationField
from django.db.models.functions import Coalesce, TruncMonth, TruncDate, Cast
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, CLINIC_TYPE_CHOICES
# import numpy as np # No longer needed here, it's in utils
from .utils import calculate_iqr_filtered_average_seconds # Import the function
from financas.models import ProcedimentoFinancas
from qualidade.models import ProcedimentoQualidade
from agenda.models import ProcedimentoDetalhes, Procedimento
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import calendar
from django.utils import timezone
from registration.models import Anesthesiologist, Surgeon
from dateutil.relativedelta import relativedelta
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
import xlsxwriter
from io import BytesIO
from qualidade.models import AvaliacaoRPA
from django.db import models as db_models

MONTH_NAMES_PT = {
    1: 'Janeiro',
    2: 'Fevereiro',
    3: 'Março',
    4: 'Abril',
    5: 'Maio',
    6: 'Junho',
    7: 'Julho',
    8: 'Agosto',
    9: 'Setembro',
    10: 'Outubro',
    11: 'Novembro',
    12: 'Dezembro',
}

@login_required
def dashboard_view(request):
    """Dashboard de Qualidade, com opção de Período Personalizado."""
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    if request.user.get_active_role() != GESTOR_USER:
        return HttpResponseForbidden("Acesso Negado")

    user_group = request.user.group
    
    # Get 'period' from URL; can be an integer (days) or 'custom'
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    selected_month = request.GET.get('month', '')
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

    # Helper function is now in dashboard/utils.py
    # def calculate_iqr_filtered_average_seconds(data_seconds_list): ...

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

    # Atraso médio (avg_delay) calculation with IQR
    delays_seconds = []
    if total_count > 0:
        for pq_item in queryset: # Renamed to avoid conflict with outer 'procedimento' variable
            if pq_item.data_horario_inicio_efetivo and pq_item.procedimento and pq_item.procedimento.data_horario:
                delay = pq_item.data_horario_inicio_efetivo - pq_item.procedimento.data_horario
                if delay.total_seconds() >= 0: # Consider only non-negative delays
                    delays_seconds.append(delay.total_seconds())
    
    avg_delay_seconds_filtered = calculate_iqr_filtered_average_seconds(delays_seconds)
    atraso_medio_formatted = None
    if avg_delay_seconds_filtered is not None:
        avg_delay_td = timedelta(seconds=avg_delay_seconds_filtered)
        days = avg_delay_td.days
        hours, remainder = divmod(avg_delay_td.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0:
            atraso_medio_formatted = f"{days} dias, {int(hours):02d}:{int(minutes):02d}"
        else:
            atraso_medio_formatted = f"{int(hours):02d}:{int(minutes):02d}"

    # Duração média (avg_duration) calculation with IQR
    durations_seconds = []
    if total_count > 0:
        for pq_item in queryset: # Renamed
            if pq_item.data_horario_fim_efetivo and pq_item.data_horario_inicio_efetivo:
                duration = pq_item.data_horario_fim_efetivo - pq_item.data_horario_inicio_efetivo
                if duration.total_seconds() >= 0: # Consider only non-negative durations
                     durations_seconds.append(duration.total_seconds())

    avg_duration_seconds_filtered = calculate_iqr_filtered_average_seconds(durations_seconds)
    duracao_media_formatted = None
    if avg_duration_seconds_filtered is not None:
        avg_duration_td = timedelta(seconds=avg_duration_seconds_filtered)
        # Ensure total_seconds() is used for durations that might exceed 24 hours before divmod
        total_seconds_for_duration = avg_duration_td.total_seconds()
        hours, remainder = divmod(total_seconds_for_duration, 3600)
        minutes, _ = divmod(remainder, 60)
        duracao_media_formatted = f"{int(hours):02d}:{int(minutes):02d}"

    # Monta o dicionário de métricas
    metrics = {
        'eventos_adversos': queryset.filter(eventos_adversos_graves=True).count() / total_count * 100 if total_count > 0 else None,
        'atraso_medio': atraso_medio_formatted,
        'duracao_media': duracao_media_formatted,
        'reacoes_alergicas': queryset.filter(reacao_alergica_grave=True).count() / total_count * 100 if total_count > 0 else None,
        'encaminhamentos_uti': queryset.filter(encaminhamento_uti=True).count() / total_count * 100 if total_count > 0 else None,
        'ponv': (ponv_count / ponv_total * 100) if ponv_total > 0 else None,
        'dor_pos_operatoria': (dor_count / dor_total * 100) if dor_total > 0 else None,
        'evento_adverso_evitavel': (evento_count / evento_total * 100) if evento_total > 0 else None,
        'adesao_checklist': queryset.filter(adesao_checklist=True).count() / total_count * 100 if total_count > 0 else None,
        'conformidade_protocolos': queryset.filter(conformidade_diretrizes=True).count() / total_count * 100 if total_count > 0 else None,
        'tecnicas_assepticas': queryset.filter(uso_tecnicas_assepticas=True).count() / total_count * 100 if total_count > 0 else None,
        'adesao_profilaxia_antibiotica': queryset.filter(adesao_profilaxia_antibiotica=True).count() / total_count * 100 if total_count > 0 else None,
        'adesao_prevencao_tvp_tep': queryset.filter(adesao_prevencao_tvp_tep=True).count() / total_count * 100 if total_count > 0 else None,
        'csat_score': queryset.aggregate(Avg('csat_score'))['csat_score__avg'],
        'ponv_view': ponv_view,
        'evento_view': evento_view,
        'dor_view': dor_view,
        'abreviacao_jejum_percent': queryset.filter(abreviacao_jejum=True).count() / total_count * 100 if total_count > 0 else None,
        'aldrete_maior_que_8_percent': queryset.filter(escala_aldrete__gt=8).count() / total_count * 100 if total_count > 0 else None,
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
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'active_role': request.user.get_active_role(),
    })

@login_required
def financas_dashboard_view(request):
    """Dashboard de Finanças, com opção de Período Personalizado."""
    #TODO: VALORES EM GLOSA SÃO A DIFERENÇA ENTRE O VALOR FATURADO E A SOMA DE valor_recebido + valor_recuperado PARA OS COM STATUS Recurso de Glosa E Processo Finalizado
    #TODO: Se status Em Processamento, Aguardando Pagamento, considerar a soma do valor_faturado como "Em andamento" do dashboard
    #TODO: considerar como pago a soma de valor_recebido e valor_recuperado em processos com status Processo Finalizado ou Recurso de Glosa

    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    if request.user.get_active_role() != GESTOR_USER:
        return HttpResponseForbidden("Acesso Negado")

    user_group = request.user.group
    user = request.user # Get the current user

    # Retrieve query params
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    selected_month = request.GET.get('month', '')
    selected_anestesista_id = request.GET.get('anestesista') # Keep as string for comparison
    selected_cirurgiao_id = request.GET.get('cirurgiao') # Keep as string for comparison
    procedimento = request.GET.get('procedimento')
    selected_graph_type = request.GET.get('graph_type', 'ticket')
    clinic = request.GET.get('clinic')
    # Charge type filters for Valores Totais card (defaults to include all)
    include_cooperativa = request.GET.get('include_cooperativa', '1')
    include_particular = request.GET.get('include_particular', '1')
    include_hospital = request.GET.get('include_hospital', '1')
    include_via_cirurgiao = request.GET.get('include_via_cirurgiao', '1')

    # Base queryset with effective_date for filtering
    queryset = (
        ProcedimentoFinancas.objects
        .annotate(
            effective_date_for_filter=Case(
                When(procedimento__isnull=False, then=Cast('procedimento__data_horario', db_models.DateField())),
                When(procedimento__isnull=True, then='api_data_cirurgia'),
                output_field=db_models.DateField()
            )
        )
        .select_related('procedimento', 'procedimento__procedimento_principal', 'group')
        .filter(group=user_group) # Filter on ProcedimentoFinancas.group itself
    )

    # Apply clinic filter only to linked procedures
    if clinic:
        queryset = queryset.filter(procedimento__isnull=False, procedimento__tipo_clinica=clinic)

    # --- Anestesista Filtering Logic ---
    anestesistas_all = Anesthesiologist.objects.filter(group=user_group).order_by('name')
    anestesistas_for_template = anestesistas_all # Default for GESTOR/ADMIN
    current_user_anesthesiologist = None
    
    # --- Cirurgião Filtering Logic ---
    cirurgioes_all = Surgeon.objects.filter(group=user_group).order_by('name')

    # Apesar de anestesista não terem acesso ao dashboard, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
    if user.get_active_role() == ANESTESISTA_USER:
        try:
            current_user_anesthesiologist = Anesthesiologist.objects.get(user=user, group=user_group)
            anestesistas_for_template = [current_user_anesthesiologist] # Only self for dropdown
            
            # Apply filter only if the selected ID matches the logged-in anesthesiologist
            if selected_anestesista_id and str(current_user_anesthesiologist.id) == selected_anestesista_id:
                 # Filter by both cooperado and anestesistas_responsaveis fields
                 queryset = queryset.filter(
                     Q(procedimento__cooperado=current_user_anesthesiologist.id) |
                     Q(procedimento__anestesistas_responsaveis=current_user_anesthesiologist.id)
                 ).distinct()
            # If an ID is selected but doesn't match, or no ID is selected, don't filter by anesthesiologist
            # (implicitly shows 'all' relevant to the user's group)
            else:
                 selected_anestesista_id = None # Ensure 'selected_anestesista_id' is None if not filtering by self

        except Anesthesiologist.DoesNotExist:
             # Handle case where Anesthesiologist profile might be missing for the user
             anestesistas_for_template = []
             selected_anestesista_id = None # Cannot filter if profile doesn't exist

    elif user.get_active_role() in [GESTOR_USER, ADMIN_USER]:
        # Gestor/Admin can filter by any anesthesiologist
        if selected_anestesista_id:
            # Filter by both cooperado and anestesistas_responsaveis fields
            queryset = queryset.filter(
                Q(procedimento__cooperado=selected_anestesista_id) |
                Q(procedimento__anestesistas_responsaveis=selected_anestesista_id)
             ).distinct()
        # Keep anestesistas_for_template as anestesistas_all

    # --- Apply Cirurgião Filter ---
    if selected_cirurgiao_id:
        queryset = queryset.filter(procedimento__cirurgiao=selected_cirurgiao_id)

    # Filter by procedimento if given (applies after anesthesiologist and surgeon filters)
    if procedimento:
        queryset = queryset.filter(procedimento__procedimento_principal__name=procedimento)

    # -----------------------------------------------------------------------
    # 1) Figure out chart_start_date and chart_end_date
    # -----------------------------------------------------------------------
    now = timezone.now()
    chart_start_date = None
    chart_end_date = None
    selected_period = None
    selected_month_label = ''

    if period == 'month' and selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(year, month)[1]
            month_start = datetime(year, month, 1)
            month_end = datetime(year, month, last_day, 23, 59, 59)

            chart_start_date = timezone.make_aware(month_start)
            chart_end_date = timezone.make_aware(month_end)

            queryset = queryset.filter(
                effective_date_for_filter__gte=month_start.date(),
                effective_date_for_filter__lte=month_end.date()
            )

            selected_period = 'month'
            selected_month_label = f"{MONTH_NAMES_PT.get(month, str(month))} {year}"
        except (ValueError, TypeError):
            selected_month = ''
            selected_period = 180
            chart_end_date = now
            chart_start_date = now - timedelta(days=180)
            queryset = queryset.filter(effective_date_for_filter__gte=chart_start_date.date())

    # if user selected 'custom' and provided valid start/end dates
    elif period == 'custom' and start_date_str and end_date_str:
        try:
            custom_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            custom_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            # if reversed, swap
            if custom_start > custom_end:
                custom_start, custom_end = custom_end, custom_start

            chart_start_date = timezone.make_aware(custom_start)
            chart_end_date = timezone.make_aware(custom_end)

            # Filter the queryset for this custom range using effective_date_for_filter
            queryset = queryset.filter(
                effective_date_for_filter__gte=custom_start.date(),
                effective_date_for_filter__lte=custom_end.date()
            )

            selected_period = 'custom'

        except ValueError:
            # fallback to 180 days
            selected_period = 180
            chart_end_date = now
            chart_start_date = now - timedelta(days=180)
            queryset = queryset.filter(effective_date_for_filter__gte=chart_start_date.date())

    else:
        # Not custom or missing date(s). Possibly numeric.
        if not period:
            period = 180
        try:
            period_days = int(period)
            selected_period = period_days
            chart_end_date = now
            chart_start_date = now - timedelta(days=period_days)
            queryset = queryset.filter(effective_date_for_filter__gte=chart_start_date.date())
        except (ValueError, TypeError):
            # fallback
            selected_period = 180
            chart_end_date = now
            chart_start_date = now - timedelta(days=180)
            queryset = queryset.filter(effective_date_for_filter__gte=chart_start_date.date())

    # If for some reason they are still None, default them
    if not chart_start_date or not chart_end_date:
        chart_end_date = now
        chart_start_date = now - timedelta(days=180) # This will be a datetime
        selected_period = 180
        # Ensure queryset is filtered if it fell through
        if not queryset.query.where: # Simplified check, might need refinement if other filters applied
             queryset = queryset.filter(effective_date_for_filter__gte=chart_start_date.date())

    # -----------------------------------------------------------------------
    # 2) Now we have a final chart_start_date and chart_end_date
    #    Decide daily vs monthly, build the date_range
    # -----------------------------------------------------------------------
    date_range, view_type = get_date_range(chart_start_date, chart_end_date)

    # -----------------------------------------------------------------------
    # 3) Proceed with finance calculations
    # -----------------------------------------------------------------------
    total_count = queryset.count()

    # Distinct procedures
    anestesias_count = queryset.values('procedimento').distinct().count()

    # Apply charge type filters ONLY for the Valores Totais card
    totals_queryset = queryset
    included_charge_types = []
    if include_cooperativa != '0':
        included_charge_types.append('cooperativa')
    if include_particular != '0':
        included_charge_types.append('particular')
    if include_hospital != '0':
        included_charge_types.append('hospital')
    if include_via_cirurgiao != '0':
        included_charge_types.append('via_cirurgiao')
    if len(included_charge_types) > 0 and len(included_charge_types) < 4:
        totals_queryset = totals_queryset.filter(tipo_cobranca__in=included_charge_types)

    # Summations by status_pagamento using the new fields and statuses (filtered by selected charge types)
    totals_by_status = totals_queryset.values('status_pagamento').annotate(
        total=Sum('valor_faturado')
    )
    total_valor = sum(
        item['total'] for item in totals_by_status if item['total'] is not None
    ) if totals_by_status else 0

    # Calculate values based on the new business logic
    valor_pago = totals_queryset.filter(
        status_pagamento__in=['processo_finalizado', 'recurso_de_glosa']
    ).aggregate(
        total=Sum(
            Coalesce('valor_recebido', 0) + Coalesce('valor_recuperado', 0),
            output_field=db_models.DecimalField()
        )
    )['total'] or 0
    
    valor_pendente = totals_queryset.filter(
        status_pagamento__in=['em_processamento', 'aguardando_pagamento']
    ).aggregate(
        total=Sum('valor_faturado')
    )['total'] or 0
    
    valor_glosa = totals_queryset.filter(
        status_pagamento__in=['processo_finalizado', 'recurso_de_glosa']
    ).aggregate(
        total=Sum(
            F('valor_faturado') - Coalesce(F('valor_recebido'), 0) - Coalesce(F('valor_recuperado'), 0),
            output_field=db_models.DecimalField()
        )
    )['total'] or 0

    # Helper for percentage
    def percentage(part, whole):
        if whole > 0:
            return (float(part) / float(whole)) * 100
        return 0

    pago_pct = percentage(valor_pago, total_valor)
    pendente_pct = percentage(valor_pendente, total_valor)
    glosa_pct = percentage(valor_glosa, total_valor)

    # Tempo Médio de Recebimento
    paid_procedures = queryset.filter(
        status_pagamento='processo_finalizado', # Assuming 'processo_finalizado' is the target status
        data_pagamento__isnull=False,
        effective_date_for_filter__isnull=False
    )
    avg_recebimento = None
    if paid_procedures.exists():
        avg_recebimento_diff = paid_procedures.annotate(
            diff_duration=ExpressionWrapper(F('data_pagamento') - F('effective_date_for_filter'), output_field=DurationField())
        ).aggregate(avg_diff_duration=Avg('diff_duration'))['avg_diff_duration']
        
        if avg_recebimento_diff:
            avg_days = avg_recebimento_diff.days
            if avg_days >= 30:
                avg_months = avg_days // 30  # approximate
                avg_recebimento = f"{avg_months} meses"
            else:
                avg_recebimento = f"{avg_days} dias"

    # Ticket Médio
    avg_ticket = queryset.aggregate(avg_valor=Avg('valor_faturado'))['avg_valor']

    # -----------------------------------------------------------------------
    # 4) Build chart data (daily or monthly)
    # -----------------------------------------------------------------------
    if view_type == 'daily':
        # Prepare a daily map
        date_map = {
            single_day.date(): {
                'cooperativa': 0,
                'hospital': 0,
                'particular': 0,
                'via_cirurgiao': 0,
                'cortesia': 0,
            }
            for single_day in date_range
        }

        daily_data = queryset.annotate(
            date=TruncDate('effective_date_for_filter')
        ).filter(
            status_pagamento__in=['processo_finalizado', 'recurso_de_glosa'] # Filter for paid/finalized statuses
        ).values('date', 'tipo_cobranca').annotate(
            total_recebido_periodo=Sum( # Sum of received and recovered amounts
                Coalesce(F('valor_recebido'), 0) + Coalesce(F('valor_recuperado'), 0),
                output_field=db_models.DecimalField()
            )
        ).order_by('date')

        for item in daily_data:
            if item['date'] in date_map and item['tipo_cobranca']:
                tipo = item['tipo_cobranca']
                if tipo in ['cooperativa', 'hospital', 'particular', 'via_cirurgiao', 'cortesia']:
                    date_map[item['date']][tipo] = float(item['total_recebido_periodo'] or 0)

        sorted_dates = sorted(date_map.keys())
        month_labels = [d.strftime("%d/%m") for d in sorted_dates]  # daily labels

        coopanest_values = [date_map[d]['cooperativa'] for d in sorted_dates]
        hospital_values = [date_map[d]['hospital'] for d in sorted_dates]
        direta_values = [date_map[d]['particular'] for d in sorted_dates]
        via_cirurgiao_values = [date_map[d]['via_cirurgiao'] for d in sorted_dates]
        cortesia_values = [date_map[d]['cortesia'] for d in sorted_dates]

        # Calculate daily tickets and revenues
        daily_tickets = []
        daily_revenues = []
        for d_date_obj in sorted_dates: # d is a date object from sorted_dates
            day_procedures = queryset.filter(effective_date_for_filter=d_date_obj)
            day_total = day_procedures.aggregate(total=Sum('valor_faturado'))['total'] or 0
            day_count = day_procedures.count()
            average_for_day = day_total / day_count if day_count > 0 else 0
            daily_tickets.append(float(round(average_for_day, 2)))
            daily_revenues.append(float(round(day_total, 2)))

        monthly_tickets = daily_tickets
        monthly_revenues = daily_revenues

    else:
        # Monthly logic
        month_map = {}
        for m_datetime_obj in date_range: # m is a datetime object (first day of month)
            key = m_datetime_obj.strftime("%Y-%m")  # e.g. "2023-05"
            month_map[key] = {
                'cooperativa': 0,
                'hospital': 0,
                'particular': 0,
                'via_cirurgiao': 0,
                'cortesia': 0,
            }

        monthly_data = queryset.annotate(
            month=TruncMonth('effective_date_for_filter')
        ).filter(
            status_pagamento__in=['processo_finalizado', 'recurso_de_glosa'] # Filter for paid/finalized statuses
        ).values('month', 'tipo_cobranca').annotate(
            total_recebido_periodo=Sum( # Sum of received and recovered amounts
                Coalesce(F('valor_recebido'), 0) + Coalesce(F('valor_recuperado'), 0),
                output_field=db_models.DecimalField()
            )
        ).order_by('month')

        for item in monthly_data:
            if item['month'] and item['tipo_cobranca']:
                key = item['month'].strftime("%Y-%m")
                if key in month_map:
                    tipo = item['tipo_cobranca']
                    if tipo == 'cooperativa':
                        month_map[key]['cooperativa'] = float(item['total_recebido_periodo'] or 0)
                    elif tipo == 'hospital':
                        month_map[key]['hospital'] = float(item['total_recebido_periodo'] or 0)
                    elif tipo == 'particular':
                        month_map[key]['particular'] = float(item['total_recebido_periodo'] or 0)
                    elif tipo == 'via_cirurgiao':
                        month_map[key]['via_cirurgiao'] = float(item['total_recebido_periodo'] or 0)
                    elif tipo == 'cortesia':
                        month_map[key]['cortesia'] = float(item['total_recebido_periodo'] or 0)

        # Sort by actual date
        sorted_months = sorted(date_range)
        month_labels = [MONTH_NAMES_PT.get(m.month, m.strftime("%B")) for m in sorted_months]

        coopanest_values = [month_map[m.strftime("%Y-%m")]['cooperativa'] for m in sorted_months]
        hospital_values = [month_map[m.strftime("%Y-%m")]['hospital'] for m in sorted_months]
        direta_values = [month_map[m.strftime("%Y-%m")]['particular'] for m in sorted_months]
        via_cirurgiao_values = [month_map[m.strftime("%Y-%m")]['via_cirurgiao'] for m in sorted_months]
        cortesia_values = [month_map[m.strftime("%Y-%m")]['cortesia'] for m in sorted_months]

        # monthly tickets & revenues
        monthly_tickets = []
        monthly_revenues = []
        for m_datetime_obj in sorted_months: # m is a datetime object
            month_procedures = queryset.filter(
                effective_date_for_filter__year=m_datetime_obj.year,
                effective_date_for_filter__month=m_datetime_obj.month
            )
            month_total = month_procedures.aggregate(total=Sum('valor_faturado'))['total'] or 0
            month_count = month_procedures.count()
            monthly_tickets.append(
                float(round(month_total / month_count if month_count > 0 else 0, 2))
            )
            monthly_revenues.append(float(round(month_total, 2)))

    # -----------------------------------------------------------------------
    # 5) Pie Chart Data
    # -----------------------------------------------------------------------
    total_coopanest = sum(coopanest_values)
    total_hospital = sum(hospital_values)
    total_direta = sum(direta_values)
    total_via_cirurgiao = sum(via_cirurgiao_values)
    total_cortesia = sum(cortesia_values)
    total_all = total_coopanest + total_hospital + total_direta + total_via_cirurgiao + total_cortesia

    coopanest_pct = (total_coopanest / total_all * 100) if total_all > 0 else 0
    hospital_pct = (total_hospital / total_all * 100) if total_all > 0 else 0
    direta_pct = (total_direta / total_all * 100) if total_all > 0 else 0
    via_cirurgiao_pct = (total_via_cirurgiao / total_all * 100) if total_all > 0 else 0
    cortesia_pct = (total_cortesia / total_all * 100) if total_all > 0 else 0

    # -----------------------------------------------------------------------
    # 6) Additional filters (procedimentos, anestesistas)
    # -----------------------------------------------------------------------
    procedimentos = (
        ProcedimentoDetalhes.objects
        .filter(procedimento__group=user_group)
        .order_by('name').distinct()
    )
    # Note: 'anestesistas_all' holds all for calculations, 'anestesistas_for_template' for dropdown
    
    # -----------------------------------------------------------------------
    # 7) Determine 'period_total' & 'anestesista_total'
    #    Recalculate anestesista_total based on potential filtering changes
    # -----------------------------------------------------------------------
    # period_total uses the main queryset which might be filtered by date, procedure, and potentially anesthesiologist
    if selected_graph_type == 'ticket':
        period_total = queryset.aggregate(avg_valor=Avg('valor_faturado'))['avg_valor'] or 0
    else: # 'receitas'
        period_total = queryset.aggregate(total=Sum('valor_faturado'))['total'] or 0
    
    anestesista_total = 0
    # Use selected_anestesista_id which reflects the actual applied filter
    if selected_anestesista_id:
         # We already filtered the main queryset if an ID was selected and valid,
         # so period_total reflects the value for the selected anesthesiologist.
         anestesista_total = period_total
    else:
         # If no specific anesthesiologist is filtered, calculate average across all in the group
         num_anestesistas = anestesistas_all.count()
         if num_anestesistas > 0:
            # Need to calculate total for the period *without* anesthesiologist filter if GESTOR/ADMIN chose "all"
            # Or if ANESTESISTA chose "all"
            # Apply annotation and filters to ProcedimentoFinancas directly
            _unfiltered_base_qs = ProcedimentoFinancas.objects.annotate(
                effective_date_for_filter=Case(
                    When(procedimento__isnull=False, then=Cast('procedimento__data_horario', db_models.DateField())),
                    When(procedimento__isnull=True, then='api_data_cirurgia'),
                    output_field=db_models.DateField()
                )
            ).select_related('procedimento', 'procedimento__procedimento_principal', 'group')
            
            unfiltered_by_anest_queryset = _unfiltered_base_qs.filter(
                group=user_group, # Filter on ProcedimentoFinancas.group
                effective_date_for_filter__gte=chart_start_date.date(), # Use .date()
                effective_date_for_filter__lte=chart_end_date.date()    # Use .date()
            )
            if procedimento: # Apply procedure filter if present
                unfiltered_by_anest_queryset = unfiltered_by_anest_queryset.filter(procedimento__procedimento_principal__name=procedimento)

            if selected_graph_type == 'ticket':
                # Average ticket for the whole group in the period
                 if clinic:
                    unfiltered_by_anest_queryset = unfiltered_by_anest_queryset.filter(procedimento__isnull=False, procedimento__tipo_clinica=clinic)
                 group_period_total_avg = unfiltered_by_anest_queryset.aggregate(avg_valor=Avg('valor_faturado'))['avg_valor'] or 0
                 anestesista_total = group_period_total_avg # When "all" is selected, show group average ticket
            else: # 'receitas'
                 # Average revenue per anesthesiologist for the whole group in the period
                 if clinic:
                    unfiltered_by_anest_queryset = unfiltered_by_anest_queryset.filter(procedimento__isnull=False, procedimento__tipo_clinica=clinic)
                 group_period_total_sum = unfiltered_by_anest_queryset.aggregate(total=Sum('valor_faturado'))['total'] or 0
                 anestesista_total = group_period_total_sum / num_anestesistas if num_anestesistas > 0 else 0
         else:
              anestesista_total = 0 # Avoid division by zero

    # -----------------------------------------------------------------------
    # 8) Rankings and comparative data
    # -----------------------------------------------------------------------
    clinic_type_map = dict(CLINIC_TYPE_CHOICES)

    top_surgeons_qs = (
        queryset.filter(procedimento__cirurgiao__isnull=False)
        .values('procedimento__cirurgiao__id', 'procedimento__cirurgiao__name')
        .annotate(total_valor=Sum('valor_faturado'))
        .order_by('-total_valor')[:10]
    )
    top_surgeons = [
        {
            'id': item['procedimento__cirurgiao__id'],
            'name': item['procedimento__cirurgiao__name'] or 'Não informado',
            'total_valor': item['total_valor'] or 0,
        }
        for item in top_surgeons_qs
    ]

    top_clinics_qs = (
        queryset.filter(procedimento__tipo_clinica__isnull=False)
        .values('procedimento__tipo_clinica')
        .annotate(total_valor=Sum('valor_faturado'))
        .order_by('-total_valor')[:10]
    )
    top_clinics = [
        {
            'slug': item['procedimento__tipo_clinica'],
            'name': clinic_type_map.get(item['procedimento__tipo_clinica'], 'Não informado'),
            'total_valor': item['total_valor'] or 0,
        }
        for item in top_clinics_qs
    ]

    anestesista_totals = defaultdict(lambda: {
        'name': '',
        'total_valor': Decimal('0'),
        'total_anestesias': 0,
    })

    responsaveis_qs = (
        queryset.filter(procedimento__anestesistas_responsaveis__isnull=False)
        .values('procedimento__anestesistas_responsaveis__id', 'procedimento__anestesistas_responsaveis__name')
        .annotate(
            total_valor=Sum('valor_faturado'),
            total_anestesias=Count('procedimento__id', distinct=True),
        )
    )

    for item in responsaveis_qs:
        anest_id = item['procedimento__anestesistas_responsaveis__id']
        if not anest_id:
            continue
        entry = anestesista_totals[anest_id]
        entry['name'] = item['procedimento__anestesistas_responsaveis__name'] or entry['name'] or 'Não informado'
        entry['total_valor'] += item['total_valor'] or Decimal('0')
        entry['total_anestesias'] += item['total_anestesias'] or 0

    cooperado_fallback_qs = (
        queryset.filter(
            procedimento__anestesistas_responsaveis__isnull=True,
            procedimento__cooperado__isnull=False,
        )
        .values('procedimento__cooperado__id', 'procedimento__cooperado__name')
        .annotate(
            total_valor=Sum('valor_faturado'),
            total_anestesias=Count('procedimento__id', distinct=True),
        )
    )

    for item in cooperado_fallback_qs:
        anest_id = item['procedimento__cooperado__id']
        if not anest_id:
            continue
        entry = anestesista_totals[anest_id]
        entry['name'] = item['procedimento__cooperado__name'] or entry['name'] or 'Não informado'
        entry['total_valor'] += item['total_valor'] or Decimal('0')
        entry['total_anestesias'] += item['total_anestesias'] or 0

    anestesista_comparativo = sorted(
        [
            {
                'id': anest_id,
                'name': data['name'] or 'Não informado',
                'total_valor': data['total_valor'],
                'total_anestesias': data['total_anestesias'],
            }
            for anest_id, data in anestesista_totals.items()
        ],
        key=lambda item: item['total_valor'],
        reverse=True,
    )[:10]

    # -----------------------------------------------------------------------
    # 9) Build context
    # -----------------------------------------------------------------------
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

        'months': month_labels,  # daily or monthly labels
        'coopanest_values': coopanest_values,
        'hospital_values': hospital_values,
        'direta_values': direta_values,
        'via_cirurgiao_values': via_cirurgiao_values,
        'cortesia_values': cortesia_values,

        'selected_period': selected_period,  # could be int, 'custom' or 'month'
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
        'selected_month': selected_month if selected_period == 'month' else '',
        'selected_month_label': selected_month_label,

        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,

        'monthly_tickets': monthly_tickets,
        'monthly_revenues': monthly_revenues,

        'coopanest_pct': coopanest_pct,
        'hospital_pct': hospital_pct,
        'direta_pct': direta_pct,
        'via_cirurgiao_pct': via_cirurgiao_pct,
        'cortesia_pct': cortesia_pct,

        'procedimentos': procedimentos,
        'selected_procedimento': procedimento,

        'anestesistas': anestesistas_for_template, # Pass the potentially limited list for the dropdown
        'selected_anestesista': selected_anestesista_id, # Pass the ID that was actually used for filtering
        'cirurgioes': cirurgioes_all,
        'selected_cirurgiao': selected_cirurgiao_id,
        'period_total': period_total,
        'anestesista_total': anestesista_total,
        'selected_graph_type': selected_graph_type,
        'active_role': request.user.get_active_role(),
        'clinic_choices': CLINIC_TYPE_CHOICES,
        'selected_clinic': clinic,
        'include_cooperativa': include_cooperativa != '0',
        'include_particular': include_particular != '0',
        'include_hospital': include_hospital != '0',
        'include_via_cirurgiao': include_via_cirurgiao != '0',
        'top_surgeons': top_surgeons,
        'top_clinics': top_clinics,
        'anestesista_comparativo': anestesista_comparativo,
    }

    return render(request, 'dashboard_financas.html', context)

@login_required
def export_financas_excel(request):
    """Handle Excel export for financial dashboard data"""
    if not request.user.validado:
        return HttpResponse('Unauthorized', status=401)
    if request.user.get_active_role() != GESTOR_USER:
        return HttpResponse('Acesso Negado', status=403)

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
    user = request.user
    # --- Replicate filtering logic from the view ---
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    selected_month = request.GET.get('month', '')
    selected_anestesista_id = request.GET.get('anestesista')
    selected_cirurgiao_id = request.GET.get('cirurgiao')
    procedimento_filter_name = request.GET.get('procedimento') # Renamed to avoid clash
    clinic = request.GET.get('clinic')

    # Base queryset with annotation
    queryset = (
        ProcedimentoFinancas.objects
        .annotate(
            effective_date_for_filter=Case(
                When(procedimento__isnull=False, then=Cast('procedimento__data_horario', db_models.DateField())),
                When(procedimento__isnull=True, then='api_data_cirurgia'),
                output_field=db_models.DateField()
            )
        )
        .select_related('procedimento', 'procedimento__procedimento_principal', 'group')
        .filter(group=user_group) # Filter on ProcedimentoFinancas.group
    )

    if clinic:
        queryset = queryset.filter(procedimento__isnull=False, procedimento__tipo_clinica=clinic)

    # Apply Anestesista Filter based on user type
    #Apesar de anestesista não terem acesso ao dashboard, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
    if user.get_active_role() == ANESTESISTA_USER:
        try:
            current_user_anesthesiologist = Anesthesiologist.objects.get(user=user, group=user_group)
            if selected_anestesista_id and str(current_user_anesthesiologist.id) == selected_anestesista_id:
                 # Filter by both cooperado and anestesistas_responsaveis fields
                 queryset = queryset.filter(
                     Q(procedimento__cooperado=current_user_anesthesiologist.id) |
                     Q(procedimento__anestesistas_responsaveis=current_user_anesthesiologist.id)
                 ).distinct()
            # else: No filtering by anesthesiologist if "Todos" or invalid ID selected by anesthesiologist
        except Anesthesiologist.DoesNotExist:
            pass # Don't filter if profile is missing

    elif user.get_active_role() in [GESTOR_USER, ADMIN_USER]:
        if selected_anestesista_id:
            # Filter by both cooperado and anestesistas_responsaveis fields
            queryset = queryset.filter(
                Q(procedimento__cooperado=selected_anestesista_id) |
                Q(procedimento__anestesistas_responsaveis=selected_anestesista_id)
             ).distinct()

    # Apply Cirurgião Filter
    if selected_cirurgiao_id:
        queryset = queryset.filter(procedimento__cirurgiao=selected_cirurgiao_id)

    # Apply Procedure Filter
    if procedimento_filter_name:
        queryset = queryset.filter(procedimento__procedimento_principal__name=procedimento_filter_name)

    # Apply Date Filter
    now = timezone.now()
    export_start_date = None
    export_end_date = None

    if period == 'month' and selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(year, month)[1]
            export_start_date = timezone.make_aware(datetime(year, month, 1))
            export_end_date = timezone.make_aware(datetime(year, month, last_day, 23, 59, 59))
            queryset = queryset.filter(
                effective_date_for_filter__gte=export_start_date.date(),
                effective_date_for_filter__lte=export_end_date.date(),
            )
        except (ValueError, TypeError):
            period = 180  # fallback if month is invalid

    elif period == 'custom' and start_date_str and end_date_str:
        try:
            custom_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            custom_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            if custom_start > custom_end: custom_start, custom_end = custom_end, custom_start

            export_start_date = timezone.make_aware(custom_start)
            export_end_date = timezone.make_aware(custom_end)
            queryset = queryset.filter(
                effective_date_for_filter__gte=export_start_date.date(),
                effective_date_for_filter__lte=export_end_date.date()
            )
        except ValueError:
             period = 180 # fallback if custom dates are invalid

    # Handle numeric period or fallback
    if export_start_date is None: # Only if custom wasn't successful
        if not period: period = 180
        try:
            period_days = int(period)
            export_end_date = now
            export_start_date = now - timedelta(days=period_days) # datetime object
            queryset = queryset.filter(effective_date_for_filter__gte=export_start_date.date())
        except (ValueError, TypeError):
            # Final fallback
            period_days = 180 # unused, just for consistency
            export_end_date = now
            export_start_date = now - timedelta(days=180) # datetime object
            queryset = queryset.filter(effective_date_for_filter__gte=export_start_date.date())
    # --- End of replicated filtering logic ---

    # Write headers
    headers = [
        'Data', 'Procedimento', 'Anestesista(s)', 'Tipo de Cobrança',
        'Valor Faturado', 'Valor Recebido', 'Valor Recuperado', 'Valor a Recuperar',
        'Status Pagamento', 'Data de Pagamento', 'Paciente'
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
        worksheet.set_column(col, col, 20) # Adjust width

    # Write data
    row = 1
    # Order by date for clarity in Excel
    queryset = queryset.order_by('effective_date_for_filter') # Use annotated date
    for item in queryset:
        worksheet.write(row, 0, item.effective_date_for_filter.strftime('%d/%m/%Y') if item.effective_date_for_filter else '')
        
        proc_principal_name = ''
        if item.procedimento and item.procedimento.procedimento_principal:
            proc_principal_name = item.procedimento.procedimento_principal.name
        worksheet.write(row, 1, proc_principal_name)
        
        anestesistas_nomes = ''
        if item.procedimento:
            anestesistas_nomes = ', '.join([a.name for a in item.procedimento.anestesistas_responsaveis.all()])
        worksheet.write(row, 2, anestesistas_nomes)
        
        worksheet.write(row, 3, item.get_tipo_cobranca_display() if item.tipo_cobranca else '') # Use display value
        worksheet.write(row, 4, float(item.valor_faturado or 0), currency_format)
        worksheet.write(row, 5, float(item.valor_recebido or 0), currency_format)
        worksheet.write(row, 6, float(item.valor_recuperado or 0), currency_format)
        worksheet.write(row, 7, float(item.valor_acatado or 0), currency_format)
        worksheet.write(row, 8, item.get_status_pagamento_display())
        worksheet.write(row, 9, item.data_pagamento.strftime('%d/%m/%Y') if item.data_pagamento else '')
        
        paciente_nome = item.procedimento.nome_paciente if item.procedimento else item.api_paciente_nome
        worksheet.write(row, 10, paciente_nome or '')
        row += 1

    # --- Summary Sheet ---
    summary = workbook.add_worksheet('Resumo')
    summary_headers = ['Métrica', 'Valor']
    for col, header in enumerate(summary_headers):
        summary.write(0, col, header, header_format)
        summary.set_column(col, col, 25) # Adjust width

    # Calculate summary data based on the final filtered queryset
    total_count = queryset.count() # Count distinct procedures might be better if needed
    anestesias_distinct_count = queryset.values('procedimento').distinct().count()

    # Calculate financial summaries from the filtered queryset
    totals_by_status = queryset.values('status_pagamento').annotate(total=Sum('valor_faturado'))
    total_valor = sum(item['total'] for item in totals_by_status if item['total'] is not None)

    def get_status_value_from_summary(status, summary_list):
        for item in summary_list:
            if item['status_pagamento'] == status and item['total']:
                return item['total']
        return 0

    valor_pago = get_status_value_from_summary('pago', totals_by_status)
    valor_pendente = get_status_value_from_summary('pendente', totals_by_status)
    valor_glosa = get_status_value_from_summary('glosa', totals_by_status)

    # Helper for percentage
    def percentage(part, whole):
        return (float(part) / float(whole) * 100) if whole and whole > 0 else 0

    pago_pct = percentage(valor_pago, total_valor)
    pendente_pct = percentage(valor_pendente, total_valor)
    glosa_pct = percentage(valor_glosa, total_valor)

    # Average Ticket for the filtered results
    avg_ticket_filtered = queryset.aggregate(avg_valor=Avg('valor_faturado'))['avg_valor']

    summary_data = [
        ('Período Analisado', f"{export_start_date.strftime('%d/%m/%Y')} a {export_end_date.strftime('%d/%m/%Y')}" if export_start_date and export_end_date else "N/A"),
        ('Filtro Anestesista', request.GET.get('anestesista_name', 'Todos') if selected_anestesista_id else 'Todos'), # Requires passing name or fetching it
        ('Filtro Procedimento', procedimento_filter_name if procedimento_filter_name else 'Todos'),
        ('Total de Registros Financeiros', total_count),
        ('Total de Anestesias (Distintas)', anestesias_distinct_count),
        ('Valor Total Cobrado (Filtrado)', total_valor),
        ('Valor Pago (Filtrado)', valor_pago),
        ('Valor Em Andamento (Filtrado)', valor_pendente),
        ('Valor em Glosa (Filtrado)', valor_glosa),
        ('% Pago', pago_pct / 100), # Format as percentage below
        ('% Em Andamento', pendente_pct / 100),
        ('% Glosa', glosa_pct / 100),
        ('Ticket Médio (Filtrado)', avg_ticket_filtered or 0),
    ]

    # Get anesthesiologist name if filtered
    anestesista_name_for_summary = "Todos"
    if selected_anestesista_id:
        try:
            filtered_anest = Anesthesiologist.objects.get(id=selected_anestesista_id)
            anestesista_name_for_summary = filtered_anest.name
        except Anesthesiologist.DoesNotExist:
            anestesista_name_for_summary = f"ID {selected_anestesista_id} (Não encontrado)"
    # Update the summary data tuple
    summary_data[1] = ('Filtro Anestesista', anestesista_name_for_summary)


    for i, (label, value) in enumerate(summary_data, 1):
        summary.write(i, 0, label)
        if isinstance(value, (int, float)):
            if 'Valor' in label or 'Ticket' in label:
                summary.write(i, 1, value, currency_format)
            elif '%' in label:
                 # Write as fraction, apply percentage format
                summary.write(i, 1, value, percent_format)
            else: # Counts
                summary.write(i, 1, value)
        else: # Text like dates, names
            summary.write(i, 1, str(value))


    workbook.close()

    # Create the HttpResponse
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    # Make filename dynamic based on filters?
    filename = f"dashboard_financas_{now.strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response

def get_date_range(start_date, end_date):
    """
    Return a tuple: (list_of_dates, 'daily' or 'monthly'),
    deciding based on how many days lie between start_date and end_date.
    """
    # Zero out start_date time to midnight, end_date to 23:59:59 for consistency
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    diff_days = (end_date - start_date).days

    if diff_days <= 30:
        # Return a daily range
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current)
            current += timedelta(days=1)
        return date_list, 'daily'
    else:
        # Return the first day of each month
        months_list = []
        # Move 'current' to the 1st day of start_date's month
        current = start_date.replace(day=1)
        while current <= end_date:
            months_list.append(current)
            current += relativedelta(months=1)
        return months_list, 'monthly'
