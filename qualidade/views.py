from django.shortcuts import render
from django.shortcuts import render, get_object_or_404, redirect
from agenda.forms import ProcedimentoForm
from agenda.views import MONTH_NAMES_PT, get_calendar_dates, get_week_dates
from financas.models import ProcedimentoFinancas
from registration.models import CustomUser
from agenda.models import Procedimento
from constants import ADMIN_USER, ANESTESISTA_USER, GESTOR_USER, STATUS_FINISHED
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.http import JsonResponse, HttpResponseForbidden, Http404, HttpResponse
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
import os
from .forms import AvaliacaoRPAForm
from .models import AvaliacaoRPA, ProcedimentoQualidade
from django.views.decorators.http import require_POST
from .forms import ProcedimentoFinalizacaoForm
from django.contrib import messages
import pytz

@login_required
def search_qualidade(request):
    date = request.GET.get('date')
    paciente = request.GET.get('paciente')
    procedimento = request.GET.get('procedimento')

    if not request.user.validado:
        return HttpResponseForbidden("You don't have permission to view this procedure.")

    highlight_date = None
    search_type = None  # Initialize search_type

    user = CustomUser.objects.get(id=request.user.id)
    form = ProcedimentoForm(user=user)  # Initialize the form here

    if date:
        search_type = 'date'
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            # Invalid date format
            date_obj = datetime.today().date()
        procedimentos = Procedimento.objects.filter(data_horario__date=date_obj, group=request.user.group)
        view_type = 'week'
        highlight_date = date_obj
    elif paciente:
        search_type = 'paciente'
        procedimentos = Procedimento.objects.filter(nome_paciente__icontains=paciente, group=request.user.group)
        view_type = 'week'
        highlight_date = procedimentos.first().data_horario.date() if procedimentos.exists() else None
    elif procedimento:
        search_type = 'procedimento'
        procedimentos = Procedimento.objects.filter(procedimento__icontains=procedimento, group=request.user.group)
        view_type = 'week'
        highlight_date = procedimentos.first().data_horario.date() if procedimentos.exists() else None
    else:
        procedimentos = Procedimento.objects.none()
        view_type = 'month'
        highlight_date = None

    today = datetime.today().date()
    if highlight_date:
        week_day = (highlight_date.weekday() + 1) % 7
        week_start = highlight_date - timedelta(days=week_day)
    else:
        week_day = (today.weekday() + 1) % 7
        week_start = today - timedelta(days=week_day)

    # Adjust year and month based on highlight_date
    if highlight_date:
        year = highlight_date.year
        month = highlight_date.month
    else:
        year = today.year
        month = today.month

    hours = ['06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']

    if view_type == 'week':
        week_dates = get_week_dates(week_start)
    else:
        week_dates = []
        calendar_dates = get_calendar_dates(year, month)

    for procedimento in procedimentos:
        if procedimento.data_horario_fim:
            procedimento.duration = (procedimento.data_horario_fim - procedimento.data_horario).total_seconds() // 3600  # Duration in hours
        else:
            procedimento.duration = 1

    context = {
        'calendar_dates': calendar_dates if view_type == 'month' else [],
        'current_year': year,
        'current_month': month,
        'current_week_start': week_start,
        'month_name': MONTH_NAMES_PT[month],
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'hours': hours,
        'view_type': view_type,
        'week_dates': week_dates, 
        'procedimentos': procedimentos,
        'highlight_date': highlight_date,
        'search_type': search_type,
        'form': form,
    }
    return render(request, 'qualidade.html', context)


def get_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    # Check if user belongs to the same group as the procedure
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to view this procedure.")
    
    # Convert UTC times to local time
    local_tz = timezone.get_current_timezone()
    start_time = procedure.data_horario.astimezone(local_tz)
    end_time = procedure.data_horario_fim.astimezone(local_tz)

    data = {
        'procedimento_type': procedure.procedimento_type,
        'data': start_time.date().strftime('%d/%m/%Y'),
        'time': start_time.strftime('%H:%M'),
        'end_time': end_time.strftime('%H:%M'),
        'nome_paciente': procedure.nome_paciente,
        'email_paciente': procedure.email_paciente,
        'convenio': procedure.convenio,
        'cpf_paciente': procedure.cpf_paciente,
        'procedimento': procedure.procedimento,
        'hospital': procedure.hospital.id if procedure.hospital else '',
        'outro_local': procedure.outro_local,
        'cirurgiao': procedure.cirurgiao.id if procedure.cirurgiao else '',
        'anestesistas_responsaveis': [
            {'id': anestesista.id, 'name': anestesista.name}
            for anestesista in procedure.anestesistas_responsaveis.all()
        ],
        'visita_pre_anestesica': procedure.visita_pre_anestesica,
        'data_visita_pre_anestesica': procedure.data_visita_pre_anestesica.strftime('%d/%m/%Y') if procedure.data_visita_pre_anestesica else '',
        'nome_responsavel_visita': procedure.nome_responsavel_visita,
    }
    return JsonResponse(data)

def search_pacientes(request):

    if not request.user.validado:
        return JsonResponse({"error": "User not validated"}, status=403)
    
    query = request.GET.get('query', '')
    if len(query) >= 2:  # Only search if at least 2 characters are entered
        pacientes = Procedimento.objects.filter(
            Q(nome_paciente__icontains=query),
            group=request.user.group
        ).values('nome_paciente').distinct()[:10]  # Limit to 10 results
        results = [paciente['nome_paciente'] for paciente in pacientes]
        return JsonResponse(results, safe=False)
    return JsonResponse([], safe=False)


@login_required
def qualidade_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user = CustomUser.objects.get(id=request.user.id)
    
    if request.method == 'POST':
        form = ProcedimentoForm(request.POST, request.FILES, user=user)
        if form.is_valid():
            procedimento = form.save(commit=False)
            procedimento.group = user.group 
            procedimento.save()
            return redirect('agenda')
    else:
        form = ProcedimentoForm(user=user)
    
    today = datetime.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    week_start_str = request.GET.get('week_start')

    if week_start_str:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        view_type = 'week'
    else:
        view_type = 'month'
        week_day = (today.weekday() + 1) % 7
        week_start = today.date() - timedelta(days=week_day)

    hours = ['06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']

    if view_type == 'week':
        week_dates = get_week_dates(week_start)
        calendar_dates = []
    else:
        calendar_dates = get_calendar_dates(year, month)
        week_dates = []

    procedimentos = Procedimento.objects.filter(group=request.user.group).prefetch_related('anestesistas_responsaveis')
    

    for procedimento in procedimentos:
        if procedimento.data_horario_fim:
            procedimento.duration = (procedimento.data_horario_fim - procedimento.data_horario).total_seconds() // 3600  # Duration in hours
        else:
            procedimento.duration = 1
    
    context = {
        'calendar_dates': calendar_dates,
        'current_year': year,
        'current_month': month,
        'current_week_start': week_start,
        'month_name': MONTH_NAMES_PT[month],
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'hours': hours,
        'view_type': view_type,
        'week_dates': week_dates, 
        'procedimentos': procedimentos,
        'form': form,
        'mini_calendar_year': year,
        'mini_calendar_month': month,
    }
    
    return render(request, 'qualidade.html', context)

@login_required
def serve_protected_file(request, file_path):
    # Check if the user is authenticated and validated
    if not request.user.is_authenticated or not request.user.validado:
        raise Http404("You don't have permission to access this file.")

    # Get the procedure associated with this file
    procedure = get_object_or_404(Procedimento, foto_anexo=file_path)

    # Check if the user belongs to the same group as the procedure
    if request.user.group != procedure.group:
        raise Http404("You don't have permission to access this file.")

    # Serve the file
    file_path = os.path.join(settings.MEDIA_ROOT, file_path)
    if os.path.exists(file_path):
        import mimetypes
        with open(file_path, 'rb') as fh:
            # Determine the MIME type of the file
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'application/octet-stream'
            
            response = HttpResponse(fh.read(), content_type=content_type)
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response
    raise Http404

@login_required
def avaliacao_rpa(request, procedimento_id):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    procedimento = get_object_or_404(Procedimento, id=procedimento_id, group=request.user.group)
    
    try:
        avaliacao_rpa = AvaliacaoRPA.objects.get(procedimento=procedimento)
    except AvaliacaoRPA.DoesNotExist:
        avaliacao_rpa = None

    if request.method == 'POST':
        form = AvaliacaoRPAForm(request.POST, instance=avaliacao_rpa)
        if form.is_valid():
            avaliacao = form.save(commit=False)
            avaliacao.procedimento = procedimento
            avaliacao.save()
            messages.success(request, 'Avaliação RPA salva com sucesso!')
            return redirect('qualidade')  # Redirect to the qualidade page after saving
    else:
        form = AvaliacaoRPAForm(instance=avaliacao_rpa)

    context = {
        'form': form,
        'procedimento': procedimento,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    return render(request, 'avaliacao_rpa.html', context)

@login_required
def finalizar_procedimento_view(request, procedimento_id):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    procedimento = get_object_or_404(Procedimento, id=procedimento_id, group=request.user.group)
    
    # Get or create related models
    qualidade, _ = ProcedimentoQualidade.objects.get_or_create(procedimento=procedimento)
    
    # Handle multiple ProcedimentoFinancas records that might exist from conciliation
    try:
        financas = ProcedimentoFinancas.objects.get(procedimento=procedimento)
    except ProcedimentoFinancas.DoesNotExist:
        # Create a new financial record if none exists
        financas = ProcedimentoFinancas.objects.create(
            procedimento=procedimento,
            group=procedimento.group
        )
    except ProcedimentoFinancas.MultipleObjectsReturned:
        # If multiple financial records exist, get the first one
        # This can happen when conciliation creates multiple CPSAs for the same procedure
        financas = ProcedimentoFinancas.objects.filter(procedimento=procedimento).first()
    
    if request.method == 'POST':
        form = ProcedimentoFinalizacaoForm(request.POST, instance=qualidade)
        if form.is_valid():
            form.save()
            messages.success(request, 'Procedimento finalizado com sucesso!')
            return redirect('qualidade')
    else:
        initial_data = {
            # Finance defaults
            'tipo_cobranca': financas.tipo_cobranca or 'cooperativa',
            'valor_faturado': financas.valor_faturado,
            'tipo_pagamento_direto': financas.tipo_pagamento_direto,
            'data_pagamento': financas.data_pagamento,

            # Quality form defaults (pre-fill like the provided screenshot)
            # Pain and scales
            'dor_pos_operatoria': False,
            'abreviacao_jejum': False,

            # Safety/protocol adherence
            'adesao_checklist': True,
            'uso_tecnicas_assepticas': True,
            'conformidade_diretrizes': True,
            'adesao_profilaxia_antibiotica': True,
            'adesao_prevencao_tvp_tep': True,

            # Adverse events & outcomes
            'eventos_adversos_graves': False,
            'reacao_alergica_grave': False,
            'encaminhamento_uti': False,
            'evento_adverso_evitavel': False,
            'ponv': False,
        }
        
        # Pre-fill effective start and end times from the Procedimento object
        # if they are not already set in the ProcedimentoQualidade instance.
        # The form's __init__ method handles formatting for existing instance values.
        # Here, we are providing initial values from the parent 'procedimento' object.

        local_tz = pytz.timezone('America/Sao_Paulo')

        # Only pre-fill if the 'qualidade' instance doesn't already have these times.
        # If 'qualidade.data_horario_inicio_efetivo' is None, try to use 'procedimento.data_horario'.
        if not qualidade.data_horario_inicio_efetivo and procedimento.data_horario:
            # Ensure 'procedimento.data_horario' is timezone-aware (assuming UTC if naive)
            dt_inicio = procedimento.data_horario
            if timezone.is_naive(dt_inicio):
                dt_inicio = timezone.make_aware(dt_inicio, pytz.utc)
            local_inicio = dt_inicio.astimezone(local_tz)
            initial_data['data_horario_inicio_efetivo'] = local_inicio.strftime('%Y-%m-%dT%H:%M')

        # Similarly for the end time.
        if not qualidade.data_horario_fim_efetivo and procedimento.data_horario_fim:
            dt_fim = procedimento.data_horario_fim
            if timezone.is_naive(dt_fim):
                dt_fim = timezone.make_aware(dt_fim, pytz.utc)
            local_fim = dt_fim.astimezone(local_tz)
            initial_data['data_horario_fim_efetivo'] = local_fim.strftime('%Y-%m-%dT%H:%M')
            
        form = ProcedimentoFinalizacaoForm(instance=qualidade, initial=initial_data)
    
    context = {
        'form': form,
        'procedimento': procedimento,
        'financas': financas,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    return render(request, 'finalizar_procedimento.html', context)
