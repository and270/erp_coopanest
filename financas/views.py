from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from .models import ProcedimentoFinancas, Despesas
from django.db.models import Q
from datetime import datetime, timedelta
from django.utils import timezone

@login_required
def financas_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user_group = request.user.group
    view_type = request.GET.get('view', 'receitas')
    status = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    # Get period parameters
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    
    # Base queryset
    if view_type == 'receitas':
        queryset = ProcedimentoFinancas.objects.filter(
            procedimento__group=user_group
        ).select_related('procedimento')
    else:
        queryset = Despesas.objects.filter(
            procedimento__group=user_group
        ).select_related('procedimento')
    
    # Apply period filter
    if period == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            
            queryset = queryset.filter(
                procedimento__data_horario__date__gte=start_date.date(),
                procedimento__data_horario__date__lte=end_date.date()
            )
            selected_period = 'custom'
        except ValueError:
            selected_period = None
    elif period:
        try:
            days = int(period)
            start_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            selected_period = period
        except ValueError:
            selected_period = None
    else:
        selected_period = None
    
    # Apply other filters
    if search_query:
        if view_type == 'receitas':
            queryset = queryset.filter(
                Q(procedimento__nome_paciente__icontains=search_query) |
                Q(procedimento__cpf_paciente__icontains=search_query)
            )
        else:
            queryset = queryset.filter(descricao__icontains=search_query)
            
    if status:
        if view_type == 'receitas':
            queryset = queryset.filter(status_pagamento=status)
        else:
            queryset = queryset.filter(status=status)
    
    context = {
        'items': queryset,
        'view_type': view_type,
        'selected_status': status,
        'search_query': search_query,
        'selected_period': selected_period,
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    
    return render(request, 'financas.html', context)
