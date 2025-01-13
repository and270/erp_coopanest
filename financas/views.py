from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED
from .models import ProcedimentoFinancas, Despesas
from django.db.models import Q
from datetime import datetime, timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
import pandas as pd
from django.http import HttpResponse

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
    
    # Base queryset with group filtering
    if view_type == 'receitas':
        queryset = ProcedimentoFinancas.objects.filter(
            procedimento__group=user_group,
            procedimento__status=STATUS_FINISHED
        ).select_related('procedimento')
    else:
        queryset = Despesas.objects.filter(
            group=user_group  # Filter despesas by group
        ).select_related('procedimento')
    
    # Apply period filter
    if period == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            
            if view_type == 'receitas':
                queryset = queryset.filter(
                    procedimento__data_horario__date__gte=start_date.date(),
                    procedimento__data_horario__date__lte=end_date.date()
                )
            else:
                queryset = queryset.filter(
                    data__gte=start_date.date(),
                    data__lte=end_date.date()
                )
            selected_period = 'custom'
        except ValueError:
            selected_period = None
    elif period:
        try:
            days = int(period)
            start_date = timezone.now() - timedelta(days=days)
            if view_type == 'receitas':
                queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            else:
                queryset = queryset.filter(data__gte=start_date.date())
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
                Q(procedimento__cpf_paciente__icontains=search_query) |
                Q(cpsa__icontains=search_query)
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

@login_required
def get_finance_item(request, type, id):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user_group = request.user.group
    
    try:
        if type == 'receitas':
            item = ProcedimentoFinancas.objects.get(
                id=id,
                procedimento__group=user_group
            )
            data = {
                'valor_cobranca': float(item.valor_cobranca) if item.valor_cobranca else 0,
                'status_pagamento': item.status_pagamento,
                'data_pagamento': item.data_pagamento.strftime('%Y-%m-%d') if item.data_pagamento else None,
                'cpf': item.procedimento.cpf_paciente,
                'cpsa': item.cpsa
            }
        else:
            item = Despesas.objects.get(
                id=id,
                group=user_group
            )
            data = {
                'descricao': item.descricao,
                'valor': float(item.valor) if item.valor else 0,
                'data': item.data.strftime('%Y-%m-%d') if item.data else None,
                'pago': item.pago
            }
        return JsonResponse(data)
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist):
        return JsonResponse({'error': 'Item não encontrado'}, status=404)

@login_required
@require_http_methods(["POST"])
def update_finance_item(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user_group = request.user.group
    
    try:
        data = request.POST
        finance_type = data.get('finance_type')
        finance_id = data.get('finance_id')
        
        if finance_type == 'receitas':
            item = ProcedimentoFinancas.objects.get(
                id=finance_id,
                procedimento__group=user_group  # Ensure user has access
            )
            item.valor_cobranca = data.get('valor_cobranca')
            item.status_pagamento = data.get('status_pagamento')
            item.data_pagamento = data.get('data_pagamento') or None
            item.cpsa = data.get('cpsa')
            if item.procedimento:
                item.procedimento.cpf_paciente = data.get('cpf')
                item.procedimento.save()
        else:
            item = Despesas.objects.get(
                id=finance_id,
                group=user_group  # Ensure user has access
            )
            item.descricao = data.get('descricao')
            item.valor = data.get('valor')
            item.pago = data.get('pago') == 'on'  # Convert checkbox value to boolean
            item.data = data.get('data')
            
        item.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["POST"])
def create_finance_item(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    try:
        data = request.POST
        finance_type = data.get('finance_type')
        
        if finance_type == 'despesas':
            # Parse the date from the form
            data_str = data.get('data')
            try:
                data_despesa = datetime.strptime(data_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False, 
                    'error': 'Data inválida'
                })
            
            item = Despesas(
                group=request.user.group,
                descricao=data.get('descricao'),
                valor=data.get('valor'),
                pago=data.get('pago') == 'on',  # Convert checkbox value to boolean
                data=data_despesa
            )
            item.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Tipo não suportado'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@login_required
def export_finances(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    view_type = request.GET.get('view', 'receitas')
    status = request.GET.get('status', '')
    search_query = request.GET.get('search', '')

    # Get period parameters
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    # Base queryset with group filtering
    if view_type == 'receitas':
        queryset = ProcedimentoFinancas.objects.filter(
            procedimento__group=request.user.group,
            procedimento__status=STATUS_FINISHED
        ).select_related('procedimento')
    else:
        queryset = Despesas.objects.filter(
            group=request.user.group  # Filter despesas by group
        ).select_related('procedimento')

    # Apply period filter
    if period == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            if view_type == 'receitas':
                queryset = queryset.filter(
                    procedimento__data_horario__date__gte=start_date.date(),
                    procedimento__data_horario__date__lte=end_date.date()
                )
            else:
                queryset = queryset.filter(
                    data__gte=start_date.date(),
                    data__lte=end_date.date()
                )
        except ValueError:
            pass
    elif period:
        try:
            days = int(period)
            start_date = timezone.now() - timedelta(days=days)
            if view_type == 'receitas':
                queryset = queryset.filter(procedimento__data_horario__gte=start_date)
            else:
                queryset = queryset.filter(data__gte=start_date.date())
        except ValueError:
            pass

    # Apply other filters
    if search_query:
        if view_type == 'receitas':
            queryset = queryset.filter(
                Q(procedimento__nome_paciente__icontains=search_query) |
                Q(procedimento__cpf_paciente__icontains=search_query) |
                Q(cpsa__icontains=search_query)
            )
        else:
            queryset = queryset.filter(descricao__icontains=search_query)

    if status:
        if view_type == 'receitas':
            queryset = queryset.filter(status_pagamento=status)
        else:
            queryset = queryset.filter(status=status)

    # Prepare data for export
    data = []
    if view_type == 'receitas':
        for item in queryset:
            data.append({
                'Paciente': item.procedimento.nome_paciente,
                'CPF': item.procedimento.cpf_paciente,
                'Data da Cirurgia': item.procedimento.data_horario.strftime('%d/%m/%Y') if item.procedimento.data_horario else '',
                'Valor': float(item.valor_cobranca) if item.valor_cobranca else 0.0,
                'Fonte Pagadora': item.get_tipo_cobranca_display(),
                'CPSA': item.cpsa or 'Ainda não informado',
                'Anestesista': item.procedimento.anestesistas_responsaveis.first().name if item.procedimento.anestesistas_responsaveis.exists() else '',
                'Situação': item.get_status_pagamento_display(),
                'Data do Pagamento': item.data_pagamento.strftime('%d/%m/%Y') if item.data_pagamento else '-',
            })
    else:
        for item in queryset:
            data.append({
                'Descrição': item.descricao,
                'Data': item.data.strftime('%d/%m/%Y') if item.data else '',
                'Valor': float(item.valor) if item.valor else 0.0,
                'Pago': 'Sim' if item.pago else 'Não',
            })

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Create an Excel file in memory
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=financas_{view_type}.xlsx'
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    return response
