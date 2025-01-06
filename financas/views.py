from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import ProcedimentoFinancas, Despesas
from django.db.models import Q

@login_required
def financas_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user_group = request.user.group
    view_type = request.GET.get('view', 'receitas')  # Default to receitas
    status = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    if view_type == 'receitas':
        queryset = ProcedimentoFinancas.objects.filter(
            procedimento__group=user_group
        ).select_related('procedimento')
        
        if search_query:
            queryset = queryset.filter(
                Q(procedimento__nome_paciente__icontains=search_query) |
                Q(procedimento__cpf_paciente__icontains=search_query)
            )
            
        if status:
            queryset = queryset.filter(status_pagamento=status)
            
    else:  # despesas
        queryset = Despesas.objects.filter(
            procedimento__group=user_group
        ).select_related('procedimento')
        
        if search_query:
            queryset = queryset.filter(descricao__icontains=search_query)
            
        if status:
            queryset = queryset.filter(status=status)
    
    context = {
        'items': queryset,
        'view_type': view_type,
        'selected_status': status,
        'search_query': search_query,
    }
    
    return render(request, 'financas.html', context)
