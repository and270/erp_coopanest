from django.shortcuts import render, get_object_or_404, redirect
from registration.models import Anesthesiologist, CustomUser
from .models import Procedimento, EscalaAnestesiologista, ProcedimentoDetalhes
from .forms import ProcedimentoForm, EscalaForm, SingleDayEscalaForm, SurveyForm
from django.contrib.auth.decorators import login_required
from calendar import monthrange, weekday
from datetime import datetime, timedelta, date
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, PLANTONISTA_ESCALA, SUBSTITUTO_ESCALA, FERIAS_ESCALA
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.forms.utils import ErrorDict
from django.http import HttpResponse, Http404
from django.conf import settings
import os
from django.views.decorators.http import require_POST
from django.utils import timezone
import calendar
from django.db.models import Q
from django.core.mail import send_mail
from django.urls import reverse
from dal_select2.views import Select2QuerySetView

MONTH_NAMES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

@require_http_methods(["POST"])
def update_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to update this procedure.")
    
    old_email = procedure.email_paciente
    form = ProcedimentoForm(request.POST, request.FILES, instance=procedure, user=request.user)
    if form.is_valid():
        updated_procedure = form.save()
        if 'anestesistas_responsaveis' in form.cleaned_data:
            updated_procedure.anestesistas_responsaveis.set(form.cleaned_data['anestesistas_responsaveis'])
        
        updated_procedure.save()
        
        email_try = False
        email_sent = False
        email_error = None

        # Check if the email has changed and is not empty
        if updated_procedure.email_paciente and updated_procedure.email_paciente != old_email:
            email_try = True
            try:
                survey_url = request.build_absolute_uri(reverse('survey', args=[updated_procedure.nps_token]))
                subject = 'Pesquisa de Satisfação com Atendimento Anestésico em procedimento cirúrgico'
                message = f"""Prezado(a) {updated_procedure.nome_paciente},

Estamos entrando em contato para solicitar sua colaboração em um processo importante de melhoria contínua do nosso atendimento.
Você foi submetido(a) recentemente a um procedimento cirúrgico, ou está prestes a passar por um, e gostaríamos de conhecer sua opinião sobre o atendimento anestésico que recebeu ou receberá. 

Sua experiência é fundamental para nós, e seu feedback nos ajudará a aprimorar nossos serviços.

Pedimos, gentilmente, que responda a um breve questionário de avaliação de satisfação após a realização do procedimento anestésico. 

{survey_url}

Suas respostas serão tratadas com total confidencialidade e utilizadas exclusivamente para fins de melhoria do atendimento.

Agradecemos antecipadamente por sua disponibilidade e colaboração. 

Sua opinião é extremamente valiosa para nós."""
                from_email = settings.DEFAULT_FROM_EMAIL
                recipient_list = [updated_procedure.email_paciente]
                send_mail(subject, message, from_email, recipient_list)
                email_sent = True
            except Exception as e:
                email_error = str(e)
                print(f"Error sending email to patient {updated_procedure.email_paciente}: ", e)
               
        return JsonResponse({
            'success': True, 
            'message': 'Procedimento atualizado com sucesso.',
            'email_sent': email_sent,
            'email_error': email_error,
            'email_try': email_try
        })
    return JsonResponse({
        'success': False,
        'errors': ErrorDict(form.errors).as_json(),
        'message': 'Erro ao atualizar procedimento.',
    })

@require_http_methods(["POST"])
def create_procedure(request):
    if not request.user.validado:
        return HttpResponseForbidden("You don't have permission to create this procedure.")
    
    form = ProcedimentoForm(request.POST, request.FILES, user=request.user)

    if form.is_valid():
        procedure = form.save(commit=False)
        procedure.group = request.user.group
        procedure.save() 

        procedure.anestesistas_responsaveis.set(form.cleaned_data['anestesistas_responsaveis'])
        procedure.save() 

        email_sent = False
        email_error = None

        success_message = 'Procedimento criado com sucesso.'

        if procedure.email_paciente:
            try:
                survey_url = request.build_absolute_uri(reverse('survey', args=[procedure.nps_token]))
                subject = 'Pesquisa de Satisfação com Atendimento Anestésico em procedimento cirúrgico'
                message = f"""Prezado(a) {procedure.nome_paciente},

Estamos entrando em contato para solicitar sua colaboração em um processo importante de melhoria contínua do nosso atendimento.
Você foi submetido(a) recentemente a um procedimento cirúrgico, ou está prestes a passar por um, e gostaríamos de conhecer sua opinião sobre o atendimento anestésico que recebeu ou receberá. 

Sua experiência é fundamental para nós, e seu feedback nos ajudará a aprimorar nossos serviços.

Pedimos, gentilmente, que responda a um breve questionário de avaliação de satisfação após a realização do procedimento anestésico. 

{survey_url}

Suas respostas serão tratadas com total confidencialidade e utilizadas exclusivamente para fins de melhoria do atendimento.

Agradecemos antecipadamente por sua disponibilidade e colaboração. 

Sua opinião é extremamente valiosa para nós."""
                from_email = settings.DEFAULT_FROM_EMAIL
                recipient_list = [procedure.email_paciente]
                send_mail(subject, message, from_email, recipient_list)
                email_sent = True
            except Exception as e:
                email_error = str(e)
                print(f"Error sending email to patient {procedure.email_paciente}: ", e)
        else:
            success_message = 'Procedimento criado com sucesso. Email do paciente não fornecido. Você pode adicioná-lo depois'

        return JsonResponse({
            'success': True,
            'id': procedure.id,
            'message': success_message,
            'email_sent': email_sent,
            'email_error': email_error
        })
    else:
        return JsonResponse({
            'success': False,
            'errors': ErrorDict(form.errors).as_json(),
            'message': 'Erro ao criar procedimento.',
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
        'procedimento_principal': {
            'id': procedure.procedimento_principal.id,
            'text': procedure.procedimento_principal.name
        } if procedure.procedimento_principal else None,
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
    days_order = [0, 1, 2, 3, 4, 5, 6]  # Sunday to Saturday
    return [
        {
            'day_name': _(date_format(week_start + timedelta(days=i), 'D')).upper(),
            'date': (week_start + timedelta(days=i)).strftime('%d/%m'),
            'full_date': week_start + timedelta(days=i)
        } for i in range(7)
    ]

@login_required
def search_agenda(request):
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
        'SECRETARIA_USER': SECRETARIA_USER,
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
    return render(request, 'agenda.html', context)

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

from django.core.mail import send_mail
from django.conf import settings

def survey_view(request, nps_token):
    procedimento = get_object_or_404(Procedimento, nps_token=nps_token)

    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=procedimento)
        if form.is_valid():
            survey_response = form.save()
            
            # Send email to the group with the patient's response
            group_email = procedimento.group.email
            subject = f'Coopahub - Pesquisa de Satisfação - {procedimento.nome_paciente}'
            message = f"""
            Um paciente acabou de responder a pesquisa de satisfação!

            Paciente: {procedimento.nome_paciente}
            
            Respostas da pesquisa:
            1. Satisfação geral: {survey_response.get_satisfacao_geral_display()}
            2. Clareza das informações: {survey_response.get_clareza_informacoes_display()}
            3. Comunicação e disponibilidade: {survey_response.get_comunicacao_disponibilidade_display()}
            4. Conforto e segurança: {survey_response.get_conforto_seguranca_display()}
            
            Comentário adicional: {survey_response.comentario_adicional}
            
            CSAT Score: {survey_response.csat_score:.2f}%
            """
            
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [group_email]
            
            try:
                send_mail(subject, message, from_email, recipient_list)
            except Exception as e:
                print(f"Error sending email to group {group_email}: ", e)
            
            return render(request, 'survey_thanks.html')
    else:
        form = SurveyForm(instance=procedimento)

    context = {
        'form': form,
        'procedimento': procedimento,
    }
    return render(request, 'survey_form.html', context)

class ProcedureAutocomplete(Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return ProcedimentoDetalhes.objects.none()

        qs = ProcedimentoDetalhes.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs.order_by('name')

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
def escala_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user = CustomUser.objects.get(id=request.user.id)
    
    start_date_str = request.GET.get('start_date')
    if start_date_str:
        first_of_month = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        today = date.today()
        first_of_month = today.replace(day=1)

    start_date = first_of_month - timedelta(days=(first_of_month.weekday() + 1) % 7)

    last_day = calendar.monthrange(first_of_month.year, first_of_month.month)[1]
    last_day_of_month = first_of_month.replace(day=last_day)

    days_until_saturday = (5 - last_day_of_month.weekday()) % 7
    end_date = last_day_of_month + timedelta(days=days_until_saturday)

    # Update escalas query
    escalas = EscalaAnestesiologista.objects.filter(
        group=user.group,
        data__gte=start_date,
        data__lte=end_date
    )

    weeks = get_escala_week_dates(start_date, end_date)

    if request.method == 'POST':
        form = EscalaForm(request.POST, user=user)
        if form.is_valid():
            form.save(commit=True)  # Save and get the list of created objects
            return redirect('escala')
    else:
        form = EscalaForm(user=user)
        single_day_form = SingleDayEscalaForm(user=user)

    context = {
        'weeks': weeks,
        'escalas': escalas,
        'form': form,
        'single_day_form': single_day_form,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'PLANTONISTA_ESCALA': PLANTONISTA_ESCALA,
        'SUBSTITUTO_ESCALA': SUBSTITUTO_ESCALA,
        'FERIAS_ESCALA': FERIAS_ESCALA,
        'start_date': start_date,
        'end_date': end_date,
        'first_of_month': first_of_month,
        'form_errors': form.errors if request.method == 'POST' else None,
    }
    
    return render(request, 'escala.html', context)

@require_POST
@login_required
def update_escala_date(request, escala_id):
    if not request.user.validado:
        return JsonResponse({"success": False, "message": "User not validated"}, status=403)

    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if request.user.group != escala.group:
        return JsonResponse({"success": False, "message": "Permission denied"}, status=403)

    new_date_str = request.POST.get('new_date')
    if not new_date_str:
        return JsonResponse({"success": False, "message": "New date not provided"}, status=400)

    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        escala.data = new_date
        escala.save()
        return JsonResponse({"success": True, "message": "Escala updated successfully"})
    except ValueError:
        return JsonResponse({"success": False, "message": "Invalid date format"}, status=400)


@require_http_methods(["POST"])
def create_escala(request):
    if not request.user.validado:
        return HttpResponseForbidden("You don't have permission to create a scale.")
    
    form = EscalaForm(request.POST, user=request.user)
    if form.is_valid():
        escala = form.save(commit=True)
        return JsonResponse({
            'success': True,
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

@require_http_methods(["POST"])
def delete_escala(request, escala_id):
    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if not request.user.validado or request.user.group != escala.group:
        return HttpResponseForbidden("You don't have permission to delete this scale.")
    
    escala.delete()
    return JsonResponse({'success': True})

def get_escala(request, escala_id):
    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if not request.user.validado or request.user.group != escala.group:
        return HttpResponseForbidden("You don't have permission to view this scale.")
    
    anesthesiologists = Anesthesiologist.objects.filter(group=request.user.group).values('id', 'name')
    
    data = {
        'id': escala.id,
        'escala_type': escala.escala_type,
        'anestesiologista': escala.anestesiologista.id,
        'anestesiologista_name': escala.anestesiologista.name,
        'data': escala.data.strftime('%Y-%m-%d'),
        'hora_inicio': escala.hora_inicio.strftime('%H:%M'),
        'hora_fim': escala.hora_fim.strftime('%H:%M'),
        'observacoes': escala.observacoes,
        'anesthesiologists': list(anesthesiologists),
    }
    return JsonResponse(data)

def get_escala_week_dates(start_date, end_date):
    weeks = []
    current_date = start_date

    while current_date <= end_date:
        week_start = current_date
        week_end = week_start + timedelta(days=6)  # Saturday

        days = [week_start + timedelta(days=i) for i in range(7)]

        weeks.append({
            'start_date': week_start,
            'end_date': week_end,
            'days': days
        })

        current_date += timedelta(days=7)

    return weeks


@require_http_methods(["POST"])
def edit_single_day_escala(request, escala_id):
    escala = get_object_or_404(EscalaAnestesiologista, id=escala_id)
    
    if not request.user.validado or request.user.group != escala.group:
        return HttpResponseForbidden("You don't have permission to edit this scale.")
    
    form = SingleDayEscalaForm(request.POST, instance=escala, user=request.user)
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'message': 'Escala atualizada com sucesso.'})
    else:
        print("Form errors:", form.errors)  # Print form errors for debugging
        return JsonResponse({
            'success': False,
            'errors': form.errors.as_json(),
            'message': 'Erro ao atualizar escala.'
        })

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

