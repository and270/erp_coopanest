from django.shortcuts import render, get_object_or_404, redirect
from .models import Procedimento, EscalaAnestesiologista
from .forms import ProcedimentoForm, EscalaForm
from django.contrib.auth.decorators import login_required
from calendar import monthrange
from datetime import datetime, timedelta
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER

MONTH_NAMES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

def get_calendar_dates(year, month):
    first_day_of_month = datetime(year, month, 1)
    last_day_of_month = datetime(year, month, monthrange(year, month)[1])
    
    start_date = first_day_of_month - timedelta(days=first_day_of_month.weekday())

    end_date = last_day_of_month + timedelta(days=6 - last_day_of_month.weekday())
    
    current_day = start_date
    calendar_dates = []
    
    while current_day <= end_date:
        calendar_dates.append({
            'day': current_day,
            'is_current_month': current_day.month == month
        })
        current_day += timedelta(days=1)
    
    return calendar_dates

def get_week_dates(week_start):
    return [week_start + timedelta(days=i) for i in range(7)]


@login_required
def agenda_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
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
    }
    
    return render(request, 'agenda.html', context)