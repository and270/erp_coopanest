from django.shortcuts import render, get_object_or_404, redirect
from .models import Procedimento, EscalaAnestesiologista
from .forms import ProcedimentoForm, EscalaForm
from django.contrib.auth.decorators import login_required
from calendar import monthrange, weekday, SUNDAY
from datetime import datetime, timedelta
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.http import JsonResponse
from django.template.loader import render_to_string

MONTH_NAMES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

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
    
    if request.method == 'POST':
        form = ProcedimentoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('agenda')
    else:
        form = ProcedimentoForm()
    
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

    procedimentos = Procedimento.objects.all()
    
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
        'form': form
    }
    
    return render(request, 'agenda.html', context)