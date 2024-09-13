from django.shortcuts import render, get_object_or_404, redirect

from registration.models import Anesthesiologist, CustomUser
from .models import Procedimento, EscalaAnestesiologista
from .forms import ProcedimentoForm, EscalaForm
from django.contrib.auth.decorators import login_required
from calendar import monthrange, weekday, SUNDAY
from datetime import datetime, timedelta, date
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.http import JsonResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.forms.utils import ErrorDict

MONTH_NAMES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

@require_http_methods(["POST"])
def update_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    # Check if user belongs to the same group as the procedure
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to update this procedure.")
    
    form = ProcedimentoForm(request.POST, request.FILES, instance=procedure, user=request.user)
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'message': 'Procedimento atualizado com sucesso.'})
    return JsonResponse({
        'success': False,
        'errors': ErrorDict(form.errors).as_json(),
        'message': 'Erro ao atualizar procedimento.'
    })

@require_http_methods(["POST"])
def create_procedure(request):
    if not request.user.validado:
        return HttpResponseForbidden("You don't have permission to update this procedure.")
    
    form = ProcedimentoForm(request.POST, request.FILES, user=request.user)
    if form.is_valid():
        procedure = form.save(commit=False)
        procedure.group = request.user.group
        procedure.save()
        return JsonResponse({
            'success': True,
            'id': procedure.id,
            'message': 'Procedimento criado com sucesso.'
        })
    else:
        return JsonResponse({
            'success': False,
            'errors': ErrorDict(form.errors).as_json(),
            'message': 'Erro ao criar procedimento.'
        })

@require_http_methods(["POST"])
def delete_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    # Check if user belongs to the same group as the procedure
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to delete this procedure.")
    
    procedure.delete()
    return JsonResponse({'success': True})

def get_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    # Check if user belongs to the same group as the procedure
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to view this procedure.")
    
    data = {
        'procedimento_type': procedure.procedimento_type,
        'data': procedure.data_horario.strftime('%d/%m/%Y'),
        'time': procedure.data_horario.strftime('%H:%M'),
        'end_time': procedure.data_horario_fim.strftime('%H:%M'),
        'nome_paciente': procedure.nome_paciente,
        'telefone_paciente': procedure.telefone_paciente,
        'email_paciente': procedure.email_paciente,
        'procedimento': procedure.procedimento,
        'hospital': procedure.hospital.id if procedure.hospital else '',
        'outro_local': procedure.outro_local,
        'cirurgiao': procedure.cirurgiao.id if procedure.cirurgiao else '',
        'anestesista_responsavel': procedure.anestesista_responsavel.id if procedure.anestesista_responsavel else '',
        'link_nps': procedure.link_nps,
        'visita_pre_anestesica': procedure.visita_pre_anestesica,
        'data_visita_pre_anestesica': procedure.data_visita_pre_anestesica.strftime('%d/%m/%Y') if procedure.data_visita_pre_anestesica else '',
        'nome_responsavel_visita': procedure.nome_responsavel_visita,
    }
    return JsonResponse(data)

def get_calendar_dates(year, month):
    _, num_days = monthrange(year, month)
    first_day_weekday = weekday(year, month, 1)
    
    # Adjust to make Sunday the first day of the week
    first_day_weekday = (first_day_weekday + 1) % 7
    
    # Calculate the number of days from the previous month to include
    days_from_prev_month = first_day_weekday
    
    # Calculate the start date (it might be in the previous month)
    start_date = datetime(year, month, 1) - timedelta(days=days_from_prev_month)
    
    calendar_dates = []
    
    for i in range(42):  # 6 weeks * 7 days
        current_date = start_date + timedelta(days=i)
        calendar_dates.append({
            'day': current_date,
            'is_current_month': current_date.month == month
        })
    
    return calendar_dates

def get_week_dates(week_start):
    # Ensure week_start is a Sunday
    week_start -= timedelta(days=week_start.weekday() + 1)
    days_order = [0, 1, 2, 3, 4, 5, 6, ]  # Sunday to Saturday
    return [
        {
            'day_name': _(date_format(week_start + timedelta(days=days_order[i]), 'D')).upper(),
            'date': (week_start + timedelta(days=days_order[i])).strftime('%d/%m'),
            'full_date': week_start + timedelta(days=days_order[i])
        } for i in range(7)
    ]

@login_required
def agenda_view(request):
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
        calendar_dates = get_week_dates(week_start)
        view_type = 'week'
    else:
        calendar_dates = get_calendar_dates(year, month)
        view_type = 'month'
        week_start = today.date() - timedelta(days=today.weekday())

    hours = ['06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']

    if view_type == 'week':
        week_dates = get_week_dates(week_start)
    else:
        week_dates = []

    procedimentos = Procedimento.objects.filter(group=user.group)

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
        'SECRETARIA_USER': SECRETARIA_USER,
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
    
    return render(request, 'agenda.html', context)

@login_required
def get_procedimento_details(request, procedimento_id):
    procedimento = get_object_or_404(Procedimento, id=procedimento_id)
    
    if not request.user.validado or request.user.group != procedimento.group:
        return HttpResponseForbidden("You don't have permission to view this procedure.")
    
    data = {
        'nome_paciente': procedimento.nome_paciente,
        'contato_paciente': procedimento.contato_pacinete,
        'procedimento': procedimento.procedimento,
        'hospital': procedimento.hospital.name if procedimento.hospital else procedimento.outro_local,
        'data_horario': procedimento.data_horario.strftime('%d/%m/%Y %H:%M'),
        'cirurgiao': procedimento.cirurgiao.name,
        'anestesista_responsavel': procedimento.anestesista_responsavel.name,
        'link_nps': procedimento.link_nps,
        'visita_pre_anestesica': procedimento.visita_pre_anestesica,
        'data_visita_pre_anestesica': procedimento.data_visita_pre_anestesica.strftime('%d/%m/%Y') if procedimento.data_visita_pre_anestesica else None,
    }
    return JsonResponse(data)

@login_required
def escala_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user = CustomUser.objects.get(id=request.user.id)
    
    start_date_str = request.GET.get('start_date')
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        start_date = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)  # Align to Sunday

    weeks = get_escala_week_dates(start_date)

    escalas = EscalaAnestesiologista.objects.filter(
        group=user.group,
        data_inicio__lte=start_date + timedelta(days=27),
        data_fim__gte=start_date
    )

    if request.method == 'POST':
        form = EscalaForm(request.POST, user=user)
        if form.is_valid():
            escala = form.save(commit=False)
            escala.group = user.group
            escala.save()
            return redirect('escala')
    else:
        form = EscalaForm(user=user)

    context = {
        'weeks': weeks,
        'escalas': escalas,
        'form': form,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'start_date': start_date,
        'end_date': start_date + timedelta(days=27),
        'form_errors': form.errors if request.method == 'POST' else None,  # Pass form errors to the context
    }
    
    return render(request, 'escala.html', context)


@require_http_methods(["POST"])
def create_escala(request):
    if not request.user.validado:
        return HttpResponseForbidden("You don't have permission to create a scale.")
    
    form = EscalaForm(request.POST, user=request.user)
    if form.is_valid():
        escala = form.save(commit=False)
        escala.group = request.user.group
        escala.save()
        return JsonResponse({
            'success': True,
            'id': escala.id,
            'message': 'Escala criada com sucesso.'
        })
    else:
        return JsonResponse({
            'success': False,
            'errors': ErrorDict(form.errors).as_json(),
            'message': 'Erro ao criar escala.'
        })

@require_http_methods(["POST"])
def update_escala(request, escala_id):
    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if not request.user.validado or request.user.group != escala.group:
        return HttpResponseForbidden("You don't have permission to update this scale.")
    
    form = EscalaForm(request.POST, instance=escala, user=request.user)
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'message': 'Escala atualizada com sucesso.'})
    return JsonResponse({
        'success': False,
        'errors': ErrorDict(form.errors).as_json(),
        'message': 'Erro ao atualizar escala.'
    })

def get_escala(request, escala_id):
    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if not request.user.validado or request.user.group != escala.group:
        return HttpResponseForbidden("You don't have permission to view this scale.")
    
    data = {
        'escala_type': escala.escala_type,
        'anestesiologista': escala.anestesiologista.id,
        'data_inicio': escala.data_inicio.strftime('%Y-%m-%d'),
        'data_fim': escala.data_fim.strftime('%Y-%m-%d'),
        'hora_inicio': escala.hora_inicio.strftime('%H:%M'),
        'hora_fim': escala.hora_fim.strftime('%H:%M'),
        'dias_da_semana': escala.dias_da_semana,
        'observacoes': escala.observacoes,
    }
    return JsonResponse(data)

def get_escala_week_dates(start_date):
    # Adjust the start date to the previous Sunday if it's not already Sunday
    if start_date.weekday() != 6:
        start_date -= timedelta(days=start_date.weekday() + 1)

    weeks = []
    for i in range(4):  # Create four weeks
        week_start = start_date + timedelta(days=i * 7)
        week_end = week_start + timedelta(days=6)
        weeks.append({
            'start_date': week_start,
            'end_date': week_end,
            'days': [week_start + timedelta(days=x) for x in range(7)]
        })
    
    # Debug information
    print(f"get_escala_week_dates - weeks[0]['start_date']: {weeks[0]['start_date']}")
    
    return weeks
