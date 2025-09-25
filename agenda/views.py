from django.shortcuts import render, get_object_or_404, redirect
from financas.models import ProcedimentoFinancas
from qualidade.models import ProcedimentoQualidade
from registration.models import Anesthesiologist, CustomUser
from .models import Procedimento, EscalaAnestesiologista, ProcedimentoDetalhes, Convenios
from .forms import ProcedimentoForm, EscalaForm, SingleDayEscalaForm, SurveyForm
from django.contrib.auth.decorators import login_required
from calendar import monthrange, weekday
from datetime import datetime, timedelta, date
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, PLANTONISTA_ESCALA, SUBSTITUTO_ESCALA, FERIAS_ESCALA
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
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.templatetags.static import static
from django.core.mail import EmailMultiAlternatives
from email.mime.image import MIMEImage
import pandas as pd
import unicodedata
import io
import re

MONTH_NAMES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

def _send_brand_email(subject: str, html_body: str, recipients: list[str]) -> None:
    plain_body = strip_tags(html_body)
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    email.attach_alternative(html_body, "text/html")

    # Attach inline logo using CID so it renders in most email clients
    logo_file_path = os.path.join(settings.BASE_DIR, 'static', 'logo_email.png')
    if os.path.exists(logo_file_path):
        with open(logo_file_path, 'rb') as f:
            logo_bytes = f.read()
            # Create MIMEImage and set Content-ID header for inline display
            img = MIMEImage(logo_bytes)
            img.add_header('Content-ID', '<logo_email.png>')
            img.add_header('Content-Disposition', 'inline', filename='logo_email.png')
            email.attach(img)

    email.send(fail_silently=False)

@require_http_methods(["POST"])
def update_procedure(request, procedure_id):
    procedure = get_object_or_404(Procedimento, id=procedure_id)
    
    if not request.user.validado or request.user.group != procedure.group:
        return HttpResponseForbidden("You don't have permission to update this procedure.")
    
    # Debug: Print POST data
    print("UPDATE PROCEDURE - POST DATA:")
    for key, value in request.POST.items():
        print(f"{key}: {value}")
    
    print("FILES:", request.FILES)
    
    old_email = procedure.email_paciente
    form = ProcedimentoForm(request.POST, request.FILES, instance=procedure, user=request.user)
    if form.is_valid():
        # Debug: Print cleaned data
        print("FORM VALID - Cleaned data:")
        for key, value in form.cleaned_data.items():
            print(f"{key}: {value}")
        
        updated_procedure = form.save()
        
        # Debug: Check if anestesistas_responsaveis is in cleaned_data
        if 'anestesistas_responsaveis' in form.cleaned_data:
            print("SETTING ANESTHESIOLOGISTS:", form.cleaned_data['anestesistas_responsaveis'])
            updated_procedure.anestesistas_responsaveis.set(form.cleaned_data['anestesistas_responsaveis'])
        else:
            print("WARNING: anestesistas_responsaveis not in cleaned_data!")
        
        updated_procedure.save()
        
        # Debug: Print the final list of anesthesiologists
        print("FINAL ANESTHESIOLOGISTS:", list(updated_procedure.anestesistas_responsaveis.all().values_list('id', 'name')))
        
        email_try = False
        email_sent = False
        email_error = None

        if updated_procedure.email_paciente and updated_procedure.email_paciente != old_email:
            email_try = True
            try:
                survey_url = request.build_absolute_uri(reverse('survey', args=[updated_procedure.nps_token]))
                subject = 'Pesquisa de Satisfação com Atendimento Anestésico em procedimento cirúrgico'
                message_context = {
                    'logo_src': 'cid:logo_email.png',
                    'message': f"""Prezado(a) {updated_procedure.nome_paciente},

Estamos entrando em contato para solicitar sua colaboração em um processo importante de melhoria contínua do nosso atendimento.
Você foi submetido(a) recentemente a um procedimento cirúrgico, ou está prestes a passar por um, e gostaríamos de conhecer sua opinião sobre o atendimento anestésico que recebeu ou receberá. 

Sua experiência é fundamental para nós, e seu feedback nos ajudará a aprimorar nossos serviços.

Pedimos, gentilmente, que responda a um breve questionário de avaliação de satisfação após a realização do procedimento anestésico. 

<a href="{survey_url}">Acessar Questionário</a>

Suas respostas serão tratadas com total confidencialidade e utilizadas exclusivamente para fins de melhoria do atendimento.

Agradecemos antecipadamente por sua disponibilidade e colaboração. 

Sua opinião é extremamente valiosa para nós."""
                }
                html_message = render_to_string('email_templates/email_template.html', message_context)
                _send_brand_email(subject, html_message, [updated_procedure.email_paciente])
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
    
    # Debug: Print POST data
    print("CREATE PROCEDURE - POST DATA:")
    for key, value in request.POST.items():
        print(f"{key}: {value}")
    
    print("FILES:", request.FILES)
    
    form = ProcedimentoForm(request.POST, request.FILES, user=request.user)

    if form.is_valid():
        # Debug: Print cleaned data
        print("FORM VALID - Cleaned data:")
        for key, value in form.cleaned_data.items():
            print(f"{key}: {value}")
            
        procedure = form.save(commit=False)
        procedure.group = request.user.group
        procedure.save() 

        # Debug: Check if anestesistas_responsaveis is in cleaned_data
        if 'anestesistas_responsaveis' in form.cleaned_data:
            print("SETTING ANESTHESIOLOGISTS:", form.cleaned_data['anestesistas_responsaveis'])
            procedure.anestesistas_responsaveis.set(form.cleaned_data['anestesistas_responsaveis'])
        else:
            print("WARNING: anestesistas_responsaveis not in cleaned_data!")
        
        procedure.save() 

        # Debug: Print the final list of anesthesiologists
        print("FINAL ANESTHESIOLOGISTS:", list(procedure.anestesistas_responsaveis.all().values_list('id', 'name')))
        
        email_sent = False
        email_error = None

        success_message = 'Procedimento criado com sucesso.'

        if procedure.email_paciente:
            try:
                survey_url = request.build_absolute_uri(reverse('survey', args=[procedure.nps_token]))
                subject = 'Pesquisa de Satisfação com Atendimento Anestésico em procedimento cirúrgico'
                message_context = {
                    'logo_src': 'cid:logo_email.png',
                    'message': f"""Prezado(a) {procedure.nome_paciente},

Estamos entrando em contato para solicitar sua colaboração em um processo importante de melhoria contínua do nosso atendimento.
Você foi submetido(a) recentemente a um procedimento cirúrgico, ou está prestes a passar por um, e gostaríamos de conhecer sua opinião sobre o atendimento anestésico que recebeu ou receberá. 

Sua experiência é fundamental para nós, e seu feedback nos ajudará a aprimorar nossos serviços.

Pedimos, gentilmente, que responda a um breve questionário de avaliação de satisfação após a realização do procedimento anestésico. 

<a href="{survey_url}">Acessar Questionário</a>

Suas respostas serão tratadas com total confidencialidade e utilizadas exclusivamente para fins de melhoria do atendimento.

Agradecemos antecipadamente por sua disponibilidade e colaboração. 

Sua opinião é extremamente valiosa para nós."""
                }
                html_message = render_to_string('email_templates/email_template.html', message_context)
                _send_brand_email(subject, html_message, [procedure.email_paciente])
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
    end_time = procedure.data_horario_fim.astimezone(local_tz) if procedure.data_horario_fim else None

    data = {
        'procedimento_type': procedure.procedimento_type,
        'data': start_time.date().strftime('%d/%m/%Y'),
        'time': start_time.strftime('%H:%M'),
        'end_time': end_time.strftime('%H:%M') if end_time else '',
        'nome_paciente': procedure.nome_paciente,
        'email_paciente': procedure.email_paciente,
        'convenio': {
            'id': procedure.convenio.id,
            'text': procedure.convenio.name
        } if procedure.convenio else None,
        'convenio_nome_novo': '',
        'cpf_paciente': procedure.cpf_paciente,
        'procedimento_principal': {
            'id': procedure.procedimento_principal.id,
            'text': procedure.procedimento_principal.name
        } if procedure.procedimento_principal else None,
        'hospital': procedure.hospital.id if procedure.hospital else '',
        'outro_local': procedure.outro_local,
        'cirurgiao': procedure.cirurgiao.id if procedure.cirurgiao else '',
        'cirurgiao_nome': procedure.cirurgiao_nome or '',
        'anestesistas_responsaveis': [
            {'id': anestesista.id, 'name': anestesista.name}
            for anestesista in procedure.anestesistas_responsaveis.all()
        ],
        'visita_pre_anestesica': procedure.visita_pre_anestesica,
        'data_visita_pre_anestesica': procedure.data_visita_pre_anestesica.strftime('%d/%m/%Y') if procedure.data_visita_pre_anestesica else '',
        'nome_responsavel_visita': procedure.nome_responsavel_visita,
        'tipo_procedimento': procedure.tipo_procedimento,
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
        procedimentos = Procedimento.objects.filter(data_horario__date=date_obj, group=request.user.group).order_by('data_horario')
        view_type = 'week'
        highlight_date = date_obj
    elif paciente:
        search_type = 'paciente'
        procedimentos = Procedimento.objects.filter(nome_paciente__icontains=paciente, group=request.user.group).order_by('data_horario')
        view_type = 'week'
        highlight_date = procedimentos.first().data_horario.date() if procedimentos.exists() else None
    elif procedimento:
        search_type = 'procedimento'
        procedimentos = Procedimento.objects.filter(procedimento__icontains=procedimento, group=request.user.group).order_by('data_horario')
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
    # First find the procedure using the nps_token
    procedimento = get_object_or_404(Procedimento, nps_token=nps_token)
    
    # Get or create the associated ProcedimentoQualidade instance
    qualidade, _ = ProcedimentoQualidade.objects.get_or_create(procedimento=procedimento)

    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=qualidade)
        if form.is_valid():
            survey_response = form.save()
            
            # Send email to the group with the patient's response
            group_email = procedimento.group.email
            subject = f'Coopahub - Pesquisa de Satisfação - {procedimento.nome_paciente}'
            message_context = {
                'logo_src': 'cid:logo_email.png',
                'message': f"""
            Um paciente acabou de responder a pesquisa de satisfação!

            <b>Paciente:</b> {procedimento.nome_paciente}
            
            <b>Respostas da pesquisa:</b>
            <p>1. Satisfação geral: {survey_response.get_satisfacao_geral_display()}</p>
            <p>2. Clareza das informações: {survey_response.get_clareza_informacoes_display()}</p>
            <p>3. Comunicação e disponibilidade: {survey_response.get_comunicacao_disponibilidade_display()}</p>
            <p>4. Conforto e segurança: {survey_response.get_conforto_seguranca_display()}</p>
            
            <p><b>Comentário adicional:</b> {survey_response.comentario_adicional}</p>
            
            <p><b>CSAT Score:</b> {survey_response.csat_score:.2f}%</p>
            """
            }
            html_message = render_to_string('email_templates/email_template.html', message_context)
            try:
                _send_brand_email(subject, html_message, [group_email])
            except Exception as e:
                print(f"Error sending email to group {group_email}: ", e)
            
            return render(request, 'survey_thanks.html')
    else:
        form = SurveyForm(instance=qualidade)

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
            # Search in both name and codigo_procedimento
            qs = qs.filter(
                Q(name__icontains=self.q) | 
                Q(codigo_procedimento__icontains=self.q)
            )

        return qs.order_by('name')

class ConvenioAutocomplete(Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Convenios.objects.none()

        qs = Convenios.objects.all()

        if self.q:
            qs = qs.filter(name__icontains=self.q)
        else:
            # Return some results even when no query is provided
            qs = qs[:20]  # Limit to first 20 results when no search term

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

    procedimentos = Procedimento.objects.filter(group=request.user.group).prefetch_related('anestesistas_responsaveis').order_by('data_horario')
    

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


def _normalize_string(value: str) -> str:
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return value.strip().lower()


def _parse_time(value):
    """Parse time that might come as string 'HH:MM', pandas Timestamp, or float (Excel time)."""
    from datetime import time as dtime
    if pd.isna(value):
        return None
    try:
        # If already a time
        if isinstance(value, dtime):
            return value
        # If pandas Timestamp or datetime
        if hasattr(value, 'to_pydatetime'):
            dt = value.to_pydatetime()
            return dtime(hour=dt.hour, minute=dt.minute)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            # Accept HH:MM or H:MM
            match = re.match(r"^(\d{1,2}):(\d{2})$", value)
            if match:
                h = int(match.group(1))
                m = int(match.group(2))
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return dtime(hour=h, minute=m)
        # Excel time as fraction of day (float)
        if isinstance(value, (int, float)) and 0 <= value <= 1:
            total_minutes = int(round(value * 24 * 60))
            h = (total_minutes // 60) % 24
            m = total_minutes % 60
            return dtime(hour=h, minute=m)
    except Exception:
        return None
    return None


def _parse_date(value):
    """Parse date from excel cell to date object."""
    from datetime import date as ddate
    if pd.isna(value):
        return None
    try:
        if isinstance(value, ddate) and not hasattr(value, 'hour'):
            return value
        if hasattr(value, 'to_pydatetime'):
            return value.to_pydatetime().date()
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            # Try dayfirst parsing
            parsed = pd.to_datetime(value, dayfirst=True, errors='coerce')
            if pd.isna(parsed):
                return None
            return parsed.to_pydatetime().date()
        # Excel serial dates as numbers
        if isinstance(value, (int, float)):
            parsed = pd.to_datetime(value, unit='D', origin='1899-12-30', errors='coerce')
            if pd.isna(parsed):
                return None
            return parsed.to_pydatetime().date()
    except Exception:
        return None
    return None


def _parse_decimal_value(value):
    """Parse decimal value from Excel cell, handling various formats."""
    from decimal import Decimal, InvalidOperation
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            # Remove common currency symbols and formatting
            cleaned = value.strip().replace('R$', '').replace('$', '').replace(',', '').replace(' ', '')
            if not cleaned:
                return None
            return Decimal(cleaned)
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        print(f"Error parsing decimal value '{value}': {e}")
        return None


def _map_payment_type(payment_type_str):
    """Map payment type string to ProcedimentoFinancas choices."""
    if not payment_type_str:
        return None
    
    payment_type_norm = _normalize_string(payment_type_str)
    
    # Map to DIRECT_PAYMENT_CHOICES
    if any(term in payment_type_norm for term in ['cartao', 'cartão', 'card']):
        return 'cartao'
    elif any(term in payment_type_norm for term in ['cheque']):
        return 'cheque'
    elif any(term in payment_type_norm for term in ['dinheiro', 'cash', 'especie']):
        return 'dinheiro'
    elif any(term in payment_type_norm for term in ['pix']):
        return 'pix'
    elif any(term in payment_type_norm for term in ['transferencia', 'transferência', 'transfer']):
        return 'transferencia'
    elif any(term in payment_type_norm for term in ['boleto']):
        return 'boleto'
    elif any(term in payment_type_norm for term in ['cooperativa', 'coop']):
        return 'cooperativa'
    elif any(term in payment_type_norm for term in ['hospital']):
        return 'hospital'
    elif any(term in payment_type_norm for term in ['particular', 'direta', 'direct']):
        return 'particular'
    
    return None


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


@login_required
@require_http_methods(["POST"])
def import_procedures(request):
    if not request.user.validado:
        return JsonResponse({"success": False, "message": "Você não tem permissão para importar."}, status=403)

    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({"success": False, "message": "Nenhum arquivo enviado."}, status=400)

    # Only accept .xlsx for now
    if not upload.name.lower().endswith('.xlsx'):
        return JsonResponse({"success": False, "message": "Formato inválido. Envie um arquivo .xlsx."}, status=400)

    try:
        df = pd.read_excel(upload, engine='openpyxl')
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Erro ao ler Excel: {e}"}, status=400)

    # Normalize columns
    normalized_columns = {}
    for col in df.columns:
        norm = _normalize_string(col)
        normalized_columns[col] = norm

    # mapping from normalized col to our keys
    col_map = {}
    for original, norm in normalized_columns.items():
        # Time columns
        if norm in ("hora inicio", "hora_inicio", "inicio"):
            col_map['start_time'] = original
        elif norm in ("hora fim", "hora_fim", "fim"):
            col_map['end_time'] = original
        # Date columns  
        elif norm in ("data do procedimento", "data do procedimetno", "data", "data procedimento"):
            col_map['date'] = original
        # CPSA/N° CPSA columns
        elif norm in ("n guia coopanest", "cpsa", "guia coopanest", "n guia", "n° cpsa", "n cpsa", "numero cpsa"):
            col_map['cpsa'] = original
        # Patient name columns
        elif norm in ("paciente", "nome do paciente"):
            col_map['patient'] = original
        # Insurance/Plan columns
        elif norm in ("plano", "convenio", "convênio", "plano de saude", "plano de saúde"):
            col_map['plan'] = original
        # Hospital/Clinic columns
        elif norm in ("hospital", "clinica", "clínica"):
            col_map['hospital'] = original
        # Urgency columns
        elif norm in ("eletivo/urgencia", "eletivo/urgencia "):
            col_map['urgency'] = original
        # CPF columns
        elif norm == "cpf":
            col_map['cpf'] = original
        # Procedure codes columns
        elif norm in ("codigos", "codigos ", "codigo", "códigos", "código", "cirurgia"):
            col_map['codes'] = original
        # Anesthesiologist columns
        elif norm.startswith("anestesistas") or norm in ("anestesista", "cooperado"):
            col_map['anesthesiologists'] = original
        # Surgeon columns
        elif norm in ("cirurgiao", "cirurgiao...", "cirurgiao ", "cirurgiao nome", "cirurgiao(a)"):
            col_map['surgeon'] = original
        # Financial columns - new additions
        elif norm in ("forma pagamento", "forma de pagamento", "tipo pagamento"):
            col_map['payment_type'] = original
        elif norm in ("valor", "valor faturado"):
            col_map['billed_value'] = original
        elif norm in ("data recebimento", "data de recebimento", "data pagamento"):
            col_map['payment_date'] = original
        elif norm in ("valor recebido coopanest", "valor recebido", "recebido"):
            col_map['received_value'] = original
        elif norm in ("checagem miyuki", "checagem", "observacao", "observação"):
            col_map['observations'] = original

    print("[IMPORT] Normalized columns:", normalized_columns)
    print("[IMPORT] Column map:", col_map)

    required_for_minimal = ['date', 'patient']
    missing_required = [r for r in required_for_minimal if r not in col_map]
    if missing_required:
        return JsonResponse({
            "success": False,
            "message": f"Colunas obrigatórias ausentes: {', '.join(missing_required)}"
        }, status=400)

    # Skip empty rows (common in exported spreadsheets)
    original_rows = len(df)
    df = df.dropna(how='all')
    after_drop_all = len(df)
    key_cols = [col_map['date'], col_map['patient']]
    if 'start_time' in col_map:
        key_cols.append(col_map['start_time'])

    def _cell_is_empty(v):
        if v is None:
            return True
        try:
            if pd.isna(v):
                return True
        except Exception:
            pass
        if isinstance(v, str) and not v.strip():
            return True
        return False

    mask_empty_keys = df[key_cols].apply(lambda s: all(_cell_is_empty(x) for x in s), axis=1)
    skipped_empty_by_keys = int(mask_empty_keys.sum())
    df = df[~mask_empty_keys].copy()
    print(f"[IMPORT] Rows: original={original_rows}, drop_all_empty={original_rows - after_drop_all}, drop_empty_keys={skipped_empty_by_keys}, final={len(df)}")

    created = 0
    updated_financas = 0
    row_results = []

    from django.utils import timezone as dj_tz
    from registration.models import HospitalClinic, Surgeon

    print("[IMPORT] Current timezone:", dj_tz.get_current_timezone())

    for idx, row in df.iterrows():
        row_number = idx + 2  # assuming header at row 1
        errors = []
        warnings = []

        try:
            # Extract values
            date_value = row.get(col_map.get('date'))
            start_value = row.get(col_map.get('start_time'))
            end_value = row.get(col_map.get('end_time')) if 'end_time' in col_map else None
            patient_name = str(row.get(col_map.get('patient')) or '').strip()
            cpf_value = str(row.get(col_map.get('cpf')) or '').strip()
            plan_value = str(row.get(col_map.get('plan')) or '').strip()
            hospital_value = str(row.get(col_map.get('hospital')) or '').strip()
            urgency_value = str(row.get(col_map.get('urgency')) or '').strip()
            codes_value = str(row.get(col_map.get('codes')) or '').strip()
            anesth_value = str(row.get(col_map.get('anesthesiologists')) or '').strip()
            surgeon_value = str(row.get(col_map.get('surgeon')) or '').strip()
            cpsa_value = str(row.get(col_map.get('cpsa')) or '').strip() if 'cpsa' in col_map else ''
            
            # Financial data - new columns
            payment_type_value = str(row.get(col_map.get('payment_type')) or '').strip() if 'payment_type' in col_map else ''
            billed_value_raw = row.get(col_map.get('billed_value')) if 'billed_value' in col_map else None
            payment_date_value = row.get(col_map.get('payment_date')) if 'payment_date' in col_map else None
            received_value_raw = row.get(col_map.get('received_value')) if 'received_value' in col_map else None
            observations_value = str(row.get(col_map.get('observations')) or '').strip() if 'observations' in col_map else ''

            print(f"[IMPORT][Row {row_number}] Raw values -> date:{date_value} start:{start_value} end:{end_value} paciente:{patient_name} cpf:{cpf_value} plano:{plan_value} hospital:{hospital_value} urg:{urgency_value} codigos:{codes_value} anest:{anesth_value} cirurgiao:{surgeon_value} cpsa:{cpsa_value} payment_type:{payment_type_value} billed:{billed_value_raw} received:{received_value_raw} pay_date:{payment_date_value}")

            # Parse date and times
            parsed_date = _parse_date(date_value)
            start_time = _parse_time(start_value) if start_value is not None else None
            end_time = _parse_time(end_value) if end_value is not None else None

            # Provide default times if missing
            if not start_time:
                from datetime import time as dtime
                start_time = dtime(9, 0)  # Default to 09:00
                warnings.append('Hora início não informada, usando padrão: 09:00')
            
            # Do not enforce default end_time; allow None

            print(f"[IMPORT][Row {row_number}] Parsed -> date:{parsed_date} start:{start_time} end:{end_time}")

            if not parsed_date:
                errors.append('Data inválida')
            if not patient_name:
                errors.append('Paciente ausente')

            if errors:
                print(f"[IMPORT][Row {row_number}] ERRORS ->", errors)
                row_results.append({"row": row_number, "status": "error", "errors": errors})
                continue

            # Combine date and time
            from datetime import datetime as dtdt
            start_dt = dtdt.combine(parsed_date, start_time)
            end_dt = dtdt.combine(parsed_date, end_time) if end_time else None
            if end_dt and end_dt < start_dt:
                # Assume end time is same day but later; if earlier, add 1 day
                end_dt = end_dt + timedelta(days=1)

            if dj_tz.is_naive(start_dt):
                start_dt = dj_tz.make_aware(start_dt, dj_tz.get_current_timezone())
            if end_dt and dj_tz.is_naive(end_dt):
                end_dt = dj_tz.make_aware(end_dt, dj_tz.get_current_timezone())

            print(f"[IMPORT][Row {row_number}] Aware datetimes -> start:{start_dt} end:{end_dt}")

            # Map urgency
            urgency_norm = _normalize_string(urgency_value)
            if urgency_norm.startswith('urg'):
                tipo_procedimento = 'urgencia'
            elif urgency_norm.startswith('ele'):
                tipo_procedimento = 'eletiva'
            else:
                tipo_procedimento = None

            # Parse financial data
            billed_value = _parse_decimal_value(billed_value_raw)
            received_value = _parse_decimal_value(received_value_raw)
            payment_date = _parse_date(payment_date_value)
            mapped_payment_type = _map_payment_type(payment_type_value)
            
            print(f"[IMPORT][Row {row_number}] Financial data -> billed:{billed_value} received:{received_value} payment_date:{payment_date} payment_type:{mapped_payment_type}")

            # Convenio
            convenio_obj = None
            if plan_value:
                convenio_obj, _ = Convenios.objects.get_or_create(name=plan_value)

            # Hospital or outro_local
            hospital_obj = None
            outro_local_value = None
            if hospital_value:
                hospital_obj = HospitalClinic.objects.filter(group=request.user.group, name__iexact=hospital_value).first()
                if not hospital_obj:
                    outro_local_value = hospital_value
            print(f"[IMPORT][Row {row_number}] Hospital -> obj:{hospital_obj} outro_local:{outro_local_value}")

            # Surgeon
            surgeon_obj = None
            surgeon_name_fallback = None
            if surgeon_value:
                surgeon_obj = Surgeon.objects.filter(group=request.user.group, name__iexact=surgeon_value).first()
                if not surgeon_obj:
                    surgeon_name_fallback = surgeon_value
            print(f"[IMPORT][Row {row_number}] Surgeon -> obj:{surgeon_obj} fallback_name:{surgeon_name_fallback}")

            # ProcedimentoDetalhes via codes
            procedimento_principal = None
            if codes_value:
                split_codes = re.split(r"[+;,]", codes_value)
                for code in split_codes:
                    code = code.strip()
                    if not code:
                        continue
                    procedimento_principal = ProcedimentoDetalhes.objects.filter(codigo_procedimento__iexact=code).first()
                    if procedimento_principal:
                        break
                if not procedimento_principal:
                    warnings.append('Código(s) não encontrado(s) em ProcedimentoDetalhes')
            print(f"[IMPORT][Row {row_number}] Procedimento principal -> {procedimento_principal}")

            # Deduplication: Try to find existing record first
            existing_procedimento = None
            if cpsa_value:
                pf_existing = ProcedimentoFinancas.objects.filter(
                    group=request.user.group,
                    cpsa=cpsa_value,
                    procedimento__isnull=False
                ).select_related('procedimento').first()
                if pf_existing:
                    existing_procedimento = pf_existing.procedimento
            if existing_procedimento is None:
                existing_procedimento = Procedimento.objects.filter(
                    group=request.user.group,
                    nome_paciente__iexact=patient_name,
                    data_horario=start_dt
                ).first()

            if existing_procedimento:
                print(f"[IMPORT][Row {row_number}] Found existing procedimento id={existing_procedimento.id}. Will not create duplicate.")
                procedimento = existing_procedimento

                # Optionally enrich existing with missing info
                updated_fields = []
                if not procedimento.procedimento_principal and procedimento_principal:
                    procedimento.procedimento_principal = procedimento_principal
                    updated_fields.append('procedimento_principal')
                if not procedimento.convenio and convenio_obj:
                    procedimento.convenio = convenio_obj
                    updated_fields.append('convenio')
                if not procedimento.hospital and hospital_obj:
                    procedimento.hospital = hospital_obj
                    updated_fields.append('hospital')
                if not procedimento.outro_local and outro_local_value:
                    procedimento.outro_local = outro_local_value
                    updated_fields.append('outro_local')
                if end_dt and (not procedimento.data_horario_fim or end_dt > procedimento.data_horario_fim):
                    procedimento.data_horario_fim = end_dt
                    updated_fields.append('data_horario_fim')
                if cpf_value and not procedimento.cpf_paciente:
                    procedimento.cpf_paciente = cpf_value
                    updated_fields.append('cpf_paciente')
                if tipo_procedimento and not procedimento.tipo_procedimento:
                    procedimento.tipo_procedimento = tipo_procedimento
                    updated_fields.append('tipo_procedimento')

                if updated_fields:
                    procedimento.save(update_fields=list(set(updated_fields)))
                    print(f"[IMPORT][Row {row_number}] Updated existing procedimento fields: {updated_fields}")
            else:
                # Create Procedimento
                procedimento = Procedimento(
                    group=request.user.group,
                    nome_paciente=patient_name,
                    email_paciente=None,
                    cpf_paciente=cpf_value or None,
                    convenio=convenio_obj,
                    procedimento_principal=procedimento_principal,
                    data_horario=start_dt,
                    data_horario_fim=end_dt,
                    hospital=hospital_obj,
                    outro_local=outro_local_value,
                    cirurgiao=surgeon_obj,
                    cirurgiao_nome=surgeon_name_fallback,
                    tipo_procedimento=tipo_procedimento,
                )
                procedimento.save()
                print(f"[IMPORT][Row {row_number}] Procedimento saved id={procedimento.id} date={start_dt.date()} time={start_dt.strftime('%H:%M')}")

            # Anesthesiologists (split by comma, plus, semicolon)
            added_anesth = []
            if anesth_value:
                names = [n.strip() for n in re.split(r"[+,;]", anesth_value) if n.strip()]
                for name in names:
                    anest = Anesthesiologist.objects.filter(group=request.user.group, name__iexact=name).first()
                    if anest:
                        procedimento.anestesistas_responsaveis.add(anest)
                        added_anesth.append(name)
                    else:
                        warnings.append(f"Anestesista não encontrado: {name}")
            print(f"[IMPORT][Row {row_number}] Anestesistas adicionados -> {added_anesth}")

            procedimento.save()

            # Link financial data (CPSA and new financial fields)
            if cpsa_value or billed_value or received_value or payment_date or mapped_payment_type:
                try:
                    # Build defaults with all available financial data
                    defaults = {}
                    if cpsa_value:
                        defaults["cpsa"] = cpsa_value
                    if billed_value:
                        defaults["valor_faturado"] = billed_value
                    if received_value:
                        defaults["valor_recebido"] = received_value
                    if payment_date:
                        defaults["data_pagamento"] = payment_date
                    if mapped_payment_type:
                        # Determine tipo_cobranca vs tipo_pagamento_direto
                        if mapped_payment_type in ['cooperativa', 'hospital', 'particular']:
                            defaults["tipo_cobranca"] = mapped_payment_type
                        else:
                            defaults["tipo_pagamento_direto"] = mapped_payment_type
                            defaults["tipo_cobranca"] = 'particular'  # Assume direct payment is particular
                    
                    pf, created_pf = ProcedimentoFinancas.objects.get_or_create(
                        procedimento=procedimento,
                        group=request.user.group,
                        defaults=defaults
                    )
                    
                    # Update existing record with new financial data if available
                    if not created_pf:
                        updated_fields = []
                        if cpsa_value and pf.cpsa != cpsa_value:
                            pf.cpsa = cpsa_value
                            updated_fields.append('cpsa')
                        if billed_value and not pf.valor_faturado:
                            pf.valor_faturado = billed_value
                            updated_fields.append('valor_faturado')
                        if received_value and not pf.valor_recebido:
                            pf.valor_recebido = received_value
                            updated_fields.append('valor_recebido')
                        if payment_date and not pf.data_pagamento:
                            pf.data_pagamento = payment_date
                            updated_fields.append('data_pagamento')
                        if mapped_payment_type:
                            if mapped_payment_type in ['cooperativa', 'hospital', 'particular'] and not pf.tipo_cobranca:
                                pf.tipo_cobranca = mapped_payment_type
                                updated_fields.append('tipo_cobranca')
                            elif mapped_payment_type not in ['cooperativa', 'hospital', 'particular'] and not pf.tipo_pagamento_direto:
                                pf.tipo_pagamento_direto = mapped_payment_type
                                updated_fields.append('tipo_pagamento_direto')
                                if not pf.tipo_cobranca:
                                    pf.tipo_cobranca = 'particular'
                                    updated_fields.append('tipo_cobranca')
                        
                        if updated_fields:
                            pf.save(update_fields=updated_fields)
                            print(f"[IMPORT][Row {row_number}] Updated financial fields: {updated_fields}")
                    
                    updated_financas += 1
                except Exception as e:
                    warnings.append(f"Não foi possível vincular dados financeiros: {str(e)}")

            status_flag = 'created' if existing_procedimento is None else 'existing'
            if existing_procedimento is None:
                created += 1
            row_results.append({
                "row": row_number,
                "status": status_flag,
                "warnings": warnings,
                "id": procedimento.id,
                "patient": patient_name,
                "date": start_dt.astimezone(dj_tz.get_current_timezone()).strftime('%d/%m/%Y'),
                "start": start_dt.astimezone(dj_tz.get_current_timezone()).strftime('%H:%M'),
                "end": (end_dt.astimezone(dj_tz.get_current_timezone()).strftime('%H:%M') if end_dt else None),
            })
            print(f"[IMPORT][Row {row_number}] DONE with warnings={warnings}")
        except Exception as e:
            print(f"[IMPORT][Row {row_number}] UNEXPECTED ERROR ->", repr(e))
            row_results.append({"row": row_number, "status": "error", "errors": [str(e)]})

    return JsonResponse({
        "success": True,
        "created": created,
        "financas_linked": updated_financas,
        "results": row_results
    })
