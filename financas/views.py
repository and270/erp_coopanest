from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from agenda.models import Procedimento
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED
from registration.models import Groups, Membership, Anesthesiologist
from .models import ProcedimentoFinancas, Despesas, ConciliacaoTentativa
from django.db.models import Q, Sum, F, Value
from datetime import datetime, timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
import pandas as pd
from django.http import HttpResponse
import requests
from difflib import SequenceMatcher
from django.conf import settings
from django.db import transaction

DIAS_PARA_CONCILIACAO = 90

@login_required
def financas_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user = request.user
    user_group = user.group
    view_type = request.GET.get('view', 'receitas')
    status = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    
    start_date, end_date = None, None
    selected_period = None

    # Parse period
    if period == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            selected_period = 'custom'
        except ValueError:
             start_date, end_date = None, None # Reset on error
    elif period:
        try:
            days = int(period)
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days -1) # Inclusive range
            selected_period = period
        except ValueError:
             start_date, end_date = None, None # Reset on error

    # Base queryset - Filter by group first
    if view_type == 'receitas':
        base_qs = ProcedimentoFinancas.objects.filter(
            Q(procedimento__group=user_group) | Q(group=user_group) # Linked via procedure OR directly via group FK
        ).select_related('procedimento', 'procedimento__hospital') # Select related for efficiency

        # Filter for user type
        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
            base_qs = base_qs.filter(
                Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
            )
        elif user.user_type not in [GESTOR_USER, ADMIN_USER]: # Allow ADMIN too? Assume yes for now.
            base_qs = ProcedimentoFinancas.objects.none() # Non-gestors/admins see nothing unless anesthesiologist

        # Apply period filter (check both procedure date and api date)
        if start_date and end_date:
            base_qs = base_qs.filter(
                Q(procedimento__data_horario__date__gte=start_date, procedimento__data_horario__date__lte=end_date) |
                Q(procedimento__isnull=True, api_data_cirurgia__gte=start_date, api_data_cirurgia__lte=end_date)
            )
            
        # Apply search filter (check procedure fields and api fields)
        if search_query:
            base_qs = base_qs.filter(
                Q(procedimento__nome_paciente__icontains=search_query) |
                Q(procedimento__cpf_paciente__icontains=search_query) |
                Q(cpsa__icontains=search_query) |
                Q(procedimento__isnull=True, api_paciente_nome__icontains=search_query) | # Search API name if unlinked
                Q(procedimento__isnull=True, cpsa__icontains=search_query) # Search CPSA if unlinked
            )

        # Apply status filter
        if status:
            base_qs = base_qs.filter(status_pagamento=status)

        # Order results
        queryset = base_qs.order_by(
            F('procedimento__data_horario').desc(nulls_last=True), # Prefer procedure date
            F('api_data_cirurgia').desc(nulls_last=True), # Fallback to API date
             '-id' # Final tie-breaker
        )

    else: # view_type == 'despesas'
        # Despesas logic remains largely unchanged, but ensure group filtering
        base_qs = Despesas.objects.filter(group=user_group).select_related('procedimento')

        # Filter for user type (Anesthesiologist might only see their own related expenses if logic requires)
        # Current logic shows all group expenses to Gestor/Admin, Anesthesiologist sees none directly unless linked?
        # Let's assume Gestor/Admin see all group expenses. Anesthesiologist logic might need review based on exact reqs.
        if user.user_type == ANESTESISTA_USER:
             # If Anesthesiologists should only see expenses linked to their procedures:
             # base_qs = base_qs.filter(procedimento__anestesistas_responsaveis=user.anesthesiologist)
             # If they see none, keep as is for now (or set to none())
             base_qs = Despesas.objects.none() # Assuming they don't see general expenses
        elif user.user_type not in [GESTOR_USER, ADMIN_USER]:
             base_qs = Despesas.objects.none()

        # Apply period filter
        if start_date and end_date:
            base_qs = base_qs.filter(data__gte=start_date, data__lte=end_date)

        # Apply search filter
        if search_query:
            base_qs = base_qs.filter(descricao__icontains=search_query)

        # Apply status filter (using 'pago' field for despesas)
        if status == 'pago':
            base_qs = base_qs.filter(pago=True)
        elif status == 'nao_pago':
            base_qs = base_qs.filter(pago=False)

        # Order results
        queryset = base_qs.order_by('-data', '-id')

    context = {
        'items': queryset,
        'view_type': view_type,
        'selected_status': status,
        'search_query': search_query,
        'selected_period': selected_period,
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }

    return render(request, 'financas.html', context)

@login_required
def get_finance_item(request, type, id):
    if not request.user.validado:
        # Returning JSON error as this is likely an API call from JS
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    user_group = user.group

    try:
        if type == 'receitas':
            # Fetch considering group linkage via procedure OR direct FK
            item = ProcedimentoFinancas.objects.select_related('procedimento').get(
                Q(procedimento__group=user_group) | Q(group=user_group),
                id=id
            )

            # Check access for Anesthesiologist
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome, user.anesthesiologist.name) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'error': 'Acesso negado'}, status=403)
            elif user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'error': 'Acesso negado'}, status=403)


            data = {
                'is_linked': bool(item.procedimento), # Flag to indicate if linked
                'valor_faturado': float(item.valor_faturado) if item.valor_faturado else 0,
                'valor_recebido': float(item.valor_recebido) if item.valor_recebido else 0,
                'valor_recuperado': float(item.valor_recuperado) if item.valor_recuperado else 0,
                'valor_acatado': float(item.valor_acatado) if item.valor_acatado else 0,
                'status_pagamento': item.status_pagamento,
                'data_pagamento': item.data_pagamento.strftime('%Y-%m-%d') if item.data_pagamento else None,
                'cpsa': item.cpsa,
                'tipo_cobranca': item.tipo_cobranca,
                'tipo_pagamento_direto': item.tipo_pagamento_direto,
                # Get data from procedure if linked, otherwise from api_* fields
                'paciente_nome': item.procedimento.nome_paciente if item.procedimento else item.api_paciente_nome,
                'cpf': item.procedimento.cpf_paciente if item.procedimento else None, # CPF only available if linked
                 'data_cirurgia': (item.procedimento.data_horario.strftime('%Y-%m-%d') if item.procedimento and item.procedimento.data_horario else 
                                  item.api_data_cirurgia.strftime('%Y-%m-%d') if item.api_data_cirurgia else None),
                 # Add other fields as needed by the frontend modal
            }
        else: # Despesas
            item = Despesas.objects.get(
                id=id,
                group=user_group # Assuming only Gestor/Admin access despesas directly
            )
             # Add specific permission checks for Despesas if needed
            if user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'error': 'Acesso negado'}, status=403)
                 
            data = {
                'descricao': item.descricao,
                'valor': float(item.valor) if item.valor else 0,
                'data': item.data.strftime('%Y-%m-%d') if item.data else None,
                'pago': item.pago
            }
        return JsonResponse(data)
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist):
        return JsonResponse({'error': 'Item não encontrado'}, status=404)
    except Exception as e:
        print(f"Error in get_finance_item: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Erro interno ao buscar item'}, status=500)

@login_required
@require_http_methods(["POST"])
@transaction.atomic
def update_finance_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    user_group = user.group

    try:
        data = request.POST
        finance_type = data.get('finance_type')
        finance_id = data.get('finance_id')

        if finance_type == 'receitas':
            # Lock only the ProcedimentoFinancas table ('self')
            item = ProcedimentoFinancas.objects.select_for_update(of=('self',)).get(
                 Q(procedimento__group=user_group) | Q(group=user_group),
                 id=finance_id
            )

            # Permission Check (similar to get_finance_item)
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome, user.anesthesiologist.name) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)
            elif user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

            # Update common fields
            item.valor_faturado = data.get('valor_faturado') if data.get('valor_faturado') else None
            item.valor_recebido = data.get('valor_recebido') if data.get('valor_recebido') else None
            item.valor_recuperado = data.get('valor_recuperado') if data.get('valor_recuperado') else None
            item.valor_acatado = data.get('valor_acatado') if data.get('valor_acatado') else None
            item.status_pagamento = data.get('status_pagamento')
            item.data_pagamento = data.get('data_pagamento') or None
            item.cpsa = data.get('cpsa') or None
            item.tipo_cobranca = data.get('tipo_cobranca')
            item.tipo_pagamento_direto = data.get('tipo_pagamento_direto') if data.get('tipo_cobranca') == 'particular' else None

            # Update procedure fields ONLY if linked
            if item.procedimento:
                item.procedimento.cpf_paciente = data.get('cpf') or None
                # Maybe update patient name too? item.procedimento.nome_paciente = data.get('paciente_nome')
                item.procedimento.save()
            else:
                # If unlinked, maybe update api_* fields?
                # Decide if editing unlinked item's API data is allowed/needed via this form
                # item.api_paciente_nome = data.get('paciente_nome') # Example
                pass


        elif finance_type == 'despesas':
            item = Despesas.objects.select_for_update().get(
                id=finance_id,
                group=user_group
            )
             # Permission check
            if user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

            item.descricao = data.get('descricao')
            item.valor = data.get('valor') if data.get('valor') else None
            item.pago = data.get('pago') == 'on'
            item.data = data.get('data') or None

        else:
             return JsonResponse({'success': False, 'error': 'Tipo de item inválido'}, status=400)

        item.save()
        return JsonResponse({'success': True})
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Item não encontrado'}, status=404)
    except Exception as e:
        print(f"Error in update_finance_item: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Erro interno ao atualizar item: {str(e)}'}, status=500)

@login_required
@require_http_methods(["POST"])
@transaction.atomic # Good practice for creation
def create_receita_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    user_group = user.group
    data = request.POST

    try:
        # Validate required manual fields
        api_paciente_nome = data.get('api_paciente_nome')
        api_data_cirurgia_str = data.get('api_data_cirurgia')
        tipo_cobranca = data.get('tipo_cobranca')
        cpsa = data.get('cpsa')
        status_pagamento = data.get('status_pagamento', 'em_processamento') # Default if not provided
        data_pagamento_str = data.get('data_pagamento')

        if not api_paciente_nome:
            return JsonResponse({'success': False, 'error': 'Nome do Paciente (Manual) é obrigatório.'}, status=400)
        if not api_data_cirurgia_str:
             return JsonResponse({'success': False, 'error': 'Data da Cirurgia (Manual) é obrigatória.'}, status=400)
        if tipo_cobranca == 'cooperativa' and not cpsa:
             return JsonResponse({'success': False, 'error': 'CPSA é obrigatório para tipo Cooperativa.'}, status=400)
        if (status_pagamento == 'processo_finalizado' or status_pagamento == 'recurso_de_glosa') and not data_pagamento_str:
             return JsonResponse({'success': False, 'error': 'Data de pagamento é obrigatória para o status selecionado.'}, status=400)


        # Parse dates
        try:
            api_data_cirurgia = datetime.strptime(api_data_cirurgia_str, '%Y-%m-%d').date() if api_data_cirurgia_str else None
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Data da Cirurgia (Manual) inválida.'}, status=400)
            
        try:
             data_pagamento = datetime.strptime(data_pagamento_str, '%Y-%m-%d').date() if data_pagamento_str else None
        except (ValueError, TypeError):
             return JsonResponse({'success': False, 'error': 'Data de Pagamento inválida.'}, status=400)


        # Create the new ProcedimentoFinancas instance (unlinked)
        new_receita = ProcedimentoFinancas(
            procedimento=None, # Explicitly unlinked
            group=user_group,
            api_paciente_nome=api_paciente_nome,
            api_data_cirurgia=api_data_cirurgia,
            api_cooperado_nome=data.get('api_cooperado_nome'), # Optional manual field
            api_hospital_nome=data.get('api_hospital_nome'),   # Optional manual field
            valor_faturado=data.get('valor_faturado') or None,
            valor_recebido=data.get('valor_recebido') or None,
            valor_recuperado=data.get('valor_recuperado') or None,
            valor_acatado=data.get('valor_acatado') or None,
            status_pagamento=status_pagamento,
            data_pagamento=data_pagamento,
            cpsa=cpsa or None,
            tipo_cobranca=tipo_cobranca,
            tipo_pagamento_direto=data.get('tipo_pagamento_direto') if tipo_cobranca == 'particular' else None
        )
        new_receita.save()

        return JsonResponse({'success': True})

    except Exception as e:
        print(f"Error in create_receita_item: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Erro interno ao criar receita: {str(e)}'}, status=500)

@login_required
@require_http_methods(["POST"])
def create_finance_item(request): # This view now ONLY handles Despesas
    if not request.user.validado:
        # Return JSONResponse for consistency, as JS expects it
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401) 
        # return render(request, 'usuario_nao_autenticado.html') -> This would cause the JSON error if hit

    try:
        data = request.POST
        # REMOVED finance_type check, as this view only does despesas now
        
        # Parse the date from the form
        data_str = data.get('data')
        try:
            data_despesa = datetime.strptime(data_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False, 
                'error': 'Data inválida'
            }, status=400) # Return 400 for bad request
        
        item = Despesas(
            group=request.user.group,
            descricao=data.get('descricao'),
            valor=data.get('valor') or None, # Allow None if empty
            pago=data.get('pago') == 'on',  # Convert checkbox value to boolean
            data=data_despesa
        )
        # Add basic validation for Despesas
        if not item.descricao:
             return JsonResponse({'success': False, 'error': 'Descrição é obrigatória.'}, status=400)
        if item.valor is None: # Check for None explicitly
             return JsonResponse({'success': False, 'error': 'Valor é obrigatório.'}, status=400)
        if not item.data: # Should be caught by date parsing, but double-check
             return JsonResponse({'success': False, 'error': 'Data é obrigatória.'}, status=400)

        item.save()
        return JsonResponse({'success': True})
        
    except Exception as e:
        print(f"Error creating despesa: {str(e)}") # Add logging
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f"Erro interno ao criar despesa: {str(e)}"}, status=500) # Return 500

@login_required
def export_finances(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html') # Or return error response

    user = request.user
    user_group = user.group
    view_type = request.GET.get('view', 'receitas')
    status = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    start_date, end_date = None, None

    # Parse period (copied from financas_view)
    if period == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date: start_date, end_date = end_date, start_date
        except ValueError: start_date, end_date = None, None
    elif period:
        try:
            days = int(period)
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days - 1)
        except ValueError: start_date, end_date = None, None

    # Get queryset using the same logic as financas_view
    if view_type == 'receitas':
        base_qs = ProcedimentoFinancas.objects.filter(
            Q(procedimento__group=user_group) | Q(group=user_group)
        ).select_related('procedimento', 'procedimento__hospital', 'procedimento__convenio') # Add convenio
        
        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
             base_qs = base_qs.filter(
                 Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                 Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
             )
        elif user.user_type not in [GESTOR_USER, ADMIN_USER]:
             base_qs = ProcedimentoFinancas.objects.none()

        if start_date and end_date:
             base_qs = base_qs.filter(
                 Q(procedimento__data_horario__date__gte=start_date, procedimento__data_horario__date__lte=end_date) |
                 Q(procedimento__isnull=True, api_data_cirurgia__gte=start_date, api_data_cirurgia__lte=end_date)
             )
        if search_query:
             base_qs = base_qs.filter(
                 Q(procedimento__nome_paciente__icontains=search_query) |
                 Q(procedimento__cpf_paciente__icontains=search_query) |
                 Q(cpsa__icontains=search_query) |
                 Q(procedimento__isnull=True, api_paciente_nome__icontains=search_query) |
                 Q(procedimento__isnull=True, cpsa__icontains=search_query)
             )
        if status:
             base_qs = base_qs.filter(status_pagamento=status)
        
        queryset = base_qs.order_by(
             F('procedimento__data_horario').desc(nulls_last=True), 
             F('api_data_cirurgia').desc(nulls_last=True), 
             '-id'
        )

        # Prepare data for export
        data = []
        for item in queryset:
            # Get anesthesiologist name safely
            anest_resp = item.procedimento.anestesistas_responsaveis.first() if item.procedimento else None
            anest_name = anest_resp.name if anest_resp else item.api_cooperado_nome or ''

            data.append({
                'Paciente': item.procedimento.nome_paciente if item.procedimento else item.api_paciente_nome or '',
                'CPF': item.procedimento.cpf_paciente if item.procedimento else '',
                'Data Cirurgia': (item.procedimento.data_horario.strftime('%d/%m/%Y') if item.procedimento and item.procedimento.data_horario else 
                                  item.api_data_cirurgia.strftime('%d/%m/%Y') if item.api_data_cirurgia else ''),
                'Valor Faturado': float(item.valor_faturado) if item.valor_faturado is not None else 0.0,
                'Valor Recebido': float(item.valor_recebido) if item.valor_recebido is not None else 0.0,
                'Valor Recuperado': float(item.valor_recuperado) if item.valor_recuperado is not None else 0.0,
                'Valor a Recuperar': float(item.valor_acatado) if item.valor_acatado is not None else 0.0, # Glosa?
                'Fonte Pagadora': item.get_tipo_cobranca_display() or '',
                'CPSA': item.get_cpsa_display() or '',
                'Anestesista': anest_name,
                'Situação': item.get_status_pagamento_display() or '',
                'Data do Pagamento': item.data_pagamento.strftime('%d/%m/%Y') if item.data_pagamento else '-',
                'Hospital': item.procedimento.hospital.name if item.procedimento and item.procedimento.hospital else item.api_hospital_nome or '',
                'Convênio': item.procedimento.convenio.name if item.procedimento and item.procedimento.convenio else '',
                'Vinculado': 'Sim' if item.procedimento else 'Não', # Indicate if linked
            })

    else: # view_type == 'despesas'
         # Despesas export logic remains the same, just re-apply filters
        base_qs = Despesas.objects.filter(group=user_group)
        if user.user_type == ANESTESISTA_USER: base_qs = Despesas.objects.none() # Or specific logic
        elif user.user_type not in [GESTOR_USER, ADMIN_USER]: base_qs = Despesas.objects.none()

        if start_date and end_date: base_qs = base_qs.filter(data__gte=start_date, data__lte=end_date)
        if search_query: base_qs = base_qs.filter(descricao__icontains=search_query)
        if status == 'pago': base_qs = base_qs.filter(pago=True)
        elif status == 'nao_pago': base_qs = base_qs.filter(pago=False)
        
        queryset = base_qs.order_by('-data', '-id')

        data = []
        for item in queryset:
            data.append({
                'Descrição': item.descricao,
                'Data': item.data.strftime('%d/%m/%Y') if item.data else '',
                'Valor': float(item.valor) if item.valor else 0.0,
                'Pago': 'Sim' if item.pago else 'Não',
            })

    # Create DataFrame and Excel Response
    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=financas_{view_type}_{timezone.now().strftime("%Y%m%d")}.xlsx'
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=view_type.capitalize())

    return response

@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_finance_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    user_group = user.group

    try:
        data = request.POST
        finance_type = data.get('finance_type')
        finance_id = data.get('finance_id')

        if finance_type == 'receitas':
            item = ProcedimentoFinancas.objects.get(
                 Q(procedimento__group=user_group) | Q(group=user_group),
                 id=finance_id
            )
             # Permission Check (similar to get/update)
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome, user.anesthesiologist.name) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)
            elif user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)

        elif finance_type == 'despesas':
            item = Despesas.objects.get(
                id=finance_id,
                group=user_group
            )
            if user.user_type not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)
        else:
             return JsonResponse({'success': False, 'error': 'Tipo inválido'}, status=400)

        item.delete()
        return JsonResponse({'success': True})

    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Item não encontrado'}, status=404)
    except Exception as e:
        print(f"Error deleting item: {e}")
        return JsonResponse({'success': False, 'error': f'Erro ao excluir item: {str(e)}'}, status=500)


def similar(a, b):
    if not a or not b:
        return 0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def parse_api_date(date_str):
    """Safely parses date string from API format YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        print(f"Warning: Could not parse date '{date_str}'")
        return None

def map_api_status(api_status_str):
    """Maps API status string to internal status choices."""
    if not api_status_str:
        return 'em_processamento' # Default if status is missing
    api_status = str(api_status_str).lower().strip()
    status_mapping = {
        'em processamento': 'em_processamento',
        'aguardando pagamento': 'aguardando_pagamento',
        'recurso de glosa': 'recurso_de_glosa',
        'processo finalizado': 'processo_finalizado',
        'cancelada': 'cancelada',
        # Add other potential mappings if needed
    }
    return status_mapping.get(api_status, 'em_processamento') # Default if unknown status

@login_required
@transaction.atomic # Use transaction to ensure atomicity
def conciliar_financas(request):
    if not request.user.validado:
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    group = user.group

    if not group:
        return JsonResponse({'error': 'Usuário não possui grupo associado'}, status=400)
    if not user.connection_key:
         return JsonResponse({'error': 'Chave de conexão não configurada para o usuário'}, status=400)

    # --- Initialization ---
    auto_matched_reports = []
    updated_records_count = 0
    newly_created_count = 0
    newly_linked_count = 0
    processed_cpsa_ids = set()
    api_errors = []
    print(f"--- Starting Conciliation for Group: {group.name}, User: {user.username} ---")

    try:
        # --- Fetch API Data ---
        api_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/guias/ajaxGuias.php"
        api_payload = {
            "conexao": user.connection_key,
            "periodo_de": (timezone.now() - timedelta(days=DIAS_PARA_CONCILIACAO)).strftime('%Y-%m-%d'),
            "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
            "status": "Listagem Geral"
        }
        response = requests.post(api_url, json=api_payload)
        response.raise_for_status()
        api_response_data = response.json()

        if api_response_data.get('erro') != '000':
            error_msg = f"API Error: {api_response_data.get('msg', 'Unknown API error')}"
            print(f"API Error for group {group.name}: {error_msg}")
            return JsonResponse({'error': error_msg}, status=500)

        guias = api_response_data.get('listaguias', [])
        # Filter out guides without essential idcpsa
        guias_dict = {
            str(g['idcpsa']): g for g in guias
            if g.get('idcpsa') and str(g.get('idcpsa')).strip()
        }
        print(f"API Fetch: Found {len(guias_dict)} guides with valid idcpsa.")
        # Optional: Log a sample guide if needed for structure check
        # if guias_dict: print(f"Sample API Guide: {list(guias_dict.values())[0]}")

        # --- Fetch Existing DB Data ---
        # Fetch ALL relevant procedures for the group (within a reasonable timeframe?)
        # Let's keep fetching recent procedures for matching, but not filter by financas__isnull
        cutoff_date = timezone.now().date() - timedelta(days=DIAS_PARA_CONCILIACAO + 30) # Look back a bit further for procedures
        all_procs_qs = Procedimento.objects.filter(
            group=group,
            data_horario__date__gte=cutoff_date
        ).select_related('financas', 'hospital') # Select related financas too

        # Add anesthesiologist filter if applicable
        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
            all_procs_qs = all_procs_qs.filter(anestesistas_responsaveis=user.anesthesiologist)
        
        all_procs_list = list(all_procs_qs)
        print(f"DB Fetch: Found {len(all_procs_list)} potentially relevant procedures.")

        # Fetch existing financas records with CPSA (for quick lookup and updates)
        financas_qs = ProcedimentoFinancas.objects.filter(
            Q(procedimento__group=group) | Q(group=group),
            tipo_cobranca='cooperativa'
        ).select_related('procedimento') # Keep this select_related

        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
             financas_qs = financas_qs.filter(
                 Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                 Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
             )

        financas_dict_by_cpsa = {f.cpsa: f for f in financas_qs if f.cpsa}
        print(f"DB Fetch: Found {len(financas_dict_by_cpsa)} existing financas records with CPSA.")

        # --- Processing ---
        financas_to_update = []
        financas_to_create = []
        processed_cpsa_ids = set()
        processed_proc_ids = set() # Keep track of procedures we've linked/updated finance for
        
        print("--- Processing API Guides ---")
        for cpsa_id, guia in guias_dict.items():
            print(f"Processing Guide CPSA {cpsa_id} (Paciente: {guia.get('paciente')})")
            processed_cpsa_ids.add(cpsa_id) # Mark as processed for Loop 3 logic later
            
            guia_paciente = guia.get('paciente')
            guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
            guia_cooperado = guia.get('cooperado') # For anesthesiologist check

            # Anesthesiologist Filter: Skip guide if user is Anesthesiologist and cooperado doesn't match
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                if not guia_cooperado or not similar(guia_cooperado, user.anesthesiologist.name) > 0.8:
                    print(f"  Skipping CPSA {cpsa_id}: Cooperado mismatch for user {user.username}.")
                    continue

            # --- Scenario 1: Finanças record with this CPSA already exists ---
            if cpsa_id in financas_dict_by_cpsa:
                financa = financas_dict_by_cpsa[cpsa_id]
                print(f"  Found existing Finanças ID {financa.id} with matching CPSA.")
                
                # Update its data from the guide
                updated = False
                guia_valor_faturado = guia.get('valor_faturado')
                guia_valor_recebido = guia.get('valor_recebido')
                guia_valor_recuperado = guia.get('valor_receuperado') # API typo?
                guia_valor_acatado = guia.get('valor_acatado')
                guia_status = map_api_status(guia.get('STATUS'))

                if guia_valor_faturado is not None and (financa.valor_faturado is None or financa.valor_faturado != float(guia_valor_faturado)):
                    financa.valor_faturado = guia_valor_faturado; updated = True
                if guia_valor_recebido is not None and (financa.valor_recebido is None or financa.valor_recebido != float(guia_valor_recebido)):
                    financa.valor_recebido = guia_valor_recebido; updated = True
                if guia_valor_recuperado is not None and (financa.valor_recuperado is None or financa.valor_recuperado != float(guia_valor_recuperado)):
                    financa.valor_recuperado = guia_valor_recuperado; updated = True
                if guia_valor_acatado is not None and (financa.valor_acatado is None or financa.valor_acatado != float(guia_valor_acatado)):
                    financa.valor_acatado = guia_valor_acatado; updated = True
                if guia_status and financa.status_pagamento != guia_status:
                    financa.status_pagamento = guia_status; updated = True
                if financa.api_paciente_nome != guia.get('paciente'):
                    financa.api_paciente_nome = guia.get('paciente'); updated = True
                if financa.api_hospital_nome != guia.get('hospital'):
                    financa.api_hospital_nome = guia.get('hospital'); updated = True
                if financa.api_cooperado_nome != guia.get('cooperado'):
                    financa.api_cooperado_nome = guia.get('cooperado'); updated = True
                guia_api_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa'))) # Renamed variable
                if financa.api_data_cirurgia != guia_api_date:
                    financa.api_data_cirurgia = guia_api_date; updated = True

                if updated:
                    print(f"    Marked Finanças ID {financa.id} for update.")
                    if financa not in financas_to_update: financas_to_update.append(financa)
                    updated_records_count += 1
                
                # If this existing finance record is NOT linked, try to link it now
                if not financa.procedimento:
                     print(f"    Existing Finanças ID {financa.id} is unlinked. Trying to find matching procedure...")
                     # Try to find a matching PROCEDURE for this guide's data
                     best_match_proc = None
                     highest_similarity = 0.7
                     if guia_paciente and guia_date:
                          for proc in all_procs_list:
                              if proc.id in processed_proc_ids: continue # Skip procs already handled

                              name_similarity = similar(guia_paciente, proc.nome_paciente)
                              proc_date = proc.data_horario.date() if proc.data_horario else None
                              date_diff = abs((guia_date - proc_date).days) if proc_date else float('inf')
                              # (Optional: Add comparison log here if needed)

                              exact_match = name_similarity > 0.95 and date_diff == 0
                              good_match = name_similarity > 0.85 and date_diff <= 1
                              current_similarity = name_similarity

                              if (exact_match or good_match) and current_similarity > highest_similarity:
                                  highest_similarity = current_similarity
                                  best_match_proc = proc
                          
                          if best_match_proc:
                              # Check if this proc already has a *different* finance linked
                              if best_match_proc.financas and best_match_proc.financas.id != financa.id:
                                   print(f"    WARNING: Found match Proc ID {best_match_proc.id}, but it's already linked to Finanças ID {best_match_proc.financas.id}. Skipping link for CPSA {cpsa_id}.")
                              elif not best_match_proc.financas: # Only link if proc is free
                                   print(f"    >>> Linking existing Finanças ID {financa.id} to Proc ID {best_match_proc.id} (Sim: {highest_similarity:.2f})")
                                   financa.procedimento = best_match_proc
                                   processed_proc_ids.add(best_match_proc.id) # Mark proc as handled
                                   newly_linked_count += 1
                                   if financa not in financas_to_update: financas_to_update.append(financa) # Ensure it gets saved
                          else:
                               print(f"    No suitable UNLINKED procedure found to link Finanças ID {financa.id} to.")
                     else:
                         print(f"    Cannot attempt linking Finanças ID {financa.id}: Guide missing patient/date.")
                elif financa.procedimento:
                     processed_proc_ids.add(financa.procedimento.id) # Mark the linked procedure as handled

            # --- Scenario 2: No existing financas with this CPSA. Try to find matching Procedure ---
            else:
                print(f"  No existing Finanças with CPSA {cpsa_id}. Searching for matching Procedure...")
                best_match_proc = None
                highest_similarity = 0.8 # Stricter threshold for creating/updating based on proc match

                if guia_paciente and guia_date:
                    for proc in all_procs_list:
                        if proc.id in processed_proc_ids: continue # Skip procs already handled

                        name_similarity = similar(guia_paciente, proc.nome_paciente)
                        proc_date = proc.data_horario.date() if proc.data_horario else None
                        date_diff = abs((guia_date - proc_date).days) if proc_date else float('inf')
                        print(f"    Comparing Guide CPSA {cpsa_id} with Proc ID {proc.id} (P='{proc.nome_paciente}', D='{proc_date}'): Sim={name_similarity:.2f}, Diff={date_diff}")

                        exact_match = name_similarity > 0.95 and date_diff == 0
                        good_match = name_similarity > 0.85 and date_diff <= 1
                        current_similarity = name_similarity

                        if (exact_match or good_match) and current_similarity > highest_similarity:
                            highest_similarity = current_similarity
                            best_match_proc = proc
                            print(f"      Potential Procedure match found: Proc ID {proc.id}, Sim {highest_similarity:.2f} (New Best)")

                    # --- SubScenario 2a: Matching Procedure Found ---
                    if best_match_proc:
                        processed_proc_ids.add(best_match_proc.id) # Mark proc as handled
                        # Check if this procedure ALREADY has a linked finance record
                        if best_match_proc.financas:
                             existing_linked_financa = best_match_proc.financas
                             print(f"    Found matching Proc ID {best_match_proc.id}, which is ALREADY linked to Finanças ID {existing_linked_financa.id}.")
                             print(f"    >>> Updating existing LINKED Finanças ID {existing_linked_financa.id} with data from Guide CPSA {cpsa_id}.")
                             
                             # Update the *existing linked* financa record
                             updated = False
                             # ... (Copy update logic again, applied to existing_linked_financa) ...
                             if existing_linked_financa.cpsa != cpsa_id: # Update CPSA!
                                 existing_linked_financa.cpsa = cpsa_id; updated = True
                             guia_valor_faturado = guia.get('valor_faturado')
                             # ... (rest of the update checks as in Scenario 1, applied to existing_linked_financa) ...
                             guia_valor_recebido = guia.get('valor_recebido')
                             guia_valor_recuperado = guia.get('valor_receuperado') # API typo?
                             guia_valor_acatado = guia.get('valor_acatado')
                             guia_status = map_api_status(guia.get('STATUS'))

                             if guia_valor_faturado is not None and (existing_linked_financa.valor_faturado is None or existing_linked_financa.valor_faturado != float(guia_valor_faturado)):
                                 existing_linked_financa.valor_faturado = guia_valor_faturado; updated = True
                             if guia_valor_recebido is not None and (existing_linked_financa.valor_recebido is None or existing_linked_financa.valor_recebido != float(guia_valor_recebido)):
                                 existing_linked_financa.valor_recebido = guia_valor_recebido; updated = True
                             if guia_valor_recuperado is not None and (existing_linked_financa.valor_recuperado is None or existing_linked_financa.valor_recuperado != float(guia_valor_recuperado)):
                                 existing_linked_financa.valor_recuperado = guia_valor_recuperado; updated = True
                             if guia_valor_acatado is not None and (existing_linked_financa.valor_acatado is None or existing_linked_financa.valor_acatado != float(guia_valor_acatado)):
                                 existing_linked_financa.valor_acatado = guia_valor_acatado; updated = True
                             if guia_status and existing_linked_financa.status_pagamento != guia_status:
                                 existing_linked_financa.status_pagamento = guia_status; updated = True
                             if existing_linked_financa.api_paciente_nome != guia.get('paciente'):
                                 existing_linked_financa.api_paciente_nome = guia.get('paciente'); updated = True
                             if existing_linked_financa.api_hospital_nome != guia.get('hospital'):
                                 existing_linked_financa.api_hospital_nome = guia.get('hospital'); updated = True
                             if existing_linked_financa.api_cooperado_nome != guia.get('cooperado'):
                                 existing_linked_financa.api_cooperado_nome = guia.get('cooperado'); updated = True
                             guia_api_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
                             if existing_linked_financa.api_data_cirurgia != guia_api_date:
                                 existing_linked_financa.api_data_cirurgia = guia_api_date; updated = True


                             if updated:
                                 print(f"      Marked existing LINKED Finanças ID {existing_linked_financa.id} for update.")
                                 if existing_linked_financa not in financas_to_update: financas_to_update.append(existing_linked_financa)
                                 updated_records_count += 1 # Count as update
                             # No change to newly_linked_count here, link already existed

                        # Else: Procedure exists but has no finance linked yet
                        else:
                            print(f"    Found matching Proc ID {best_match_proc.id} (unlinked).")
                            print(f"    >>> Creating NEW Finanças record for Guide CPSA {cpsa_id} and linking to Proc ID {best_match_proc.id}.")
                            new_financa = ProcedimentoFinancas(
                                procedimento=best_match_proc,
                                group=group,
                                tipo_cobranca='cooperativa',
                                cpsa=cpsa_id,
                                valor_faturado=guia.get('valor_faturado'),
                                valor_recebido=guia.get('valor_recebido'),
                                valor_recuperado=guia.get('valor_receuperado'),
                                valor_acatado=guia.get('valor_acatado'),
                                status_pagamento=map_api_status(guia.get('STATUS')),
                                api_paciente_nome=guia.get('paciente'),
                                api_data_cirurgia=parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa'))),
                                api_hospital_nome=guia.get('hospital'),
                                api_cooperado_nome=guia.get('cooperado')
                            )
                            financas_to_create.append(new_financa)
                            newly_created_count += 1
                            newly_linked_count += 1 # Counts as a link established

                    # --- SubScenario 2b: No Matching Procedure Found ---
                    else:
                        print(f"    No matching Procedure found for Guide CPSA {cpsa_id}.")
                        print(f"    >>> Creating NEW UNLINKED Finanças record for Guide CPSA {cpsa_id}.")
                        new_financa = ProcedimentoFinancas(
                             procedimento=None, # Unlinked
                             group=group,
                             tipo_cobranca='cooperativa',
                             cpsa=cpsa_id,
                             # ... (populate fields from guia as above) ...
                             valor_faturado=guia.get('valor_faturado'),
                             valor_recebido=guia.get('valor_recebido'),
                             valor_recuperado=guia.get('valor_receuperado'),
                             valor_acatado=guia.get('valor_acatado'),
                             status_pagamento=map_api_status(guia.get('STATUS')),
                             api_paciente_nome=guia.get('paciente'),
                             api_data_cirurgia=parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa'))),
                             api_hospital_nome=guia.get('hospital'),
                             api_cooperado_nome=guia.get('cooperado')
                        )
                        financas_to_create.append(new_financa)
                        newly_created_count += 1
                else:
                     print(f"    Cannot attempt matching Guide CPSA {cpsa_id}: Guide missing patient/date.")
                     # Create unlinked anyway? Or log as error? Let's create unlinked for now if CPSA exists.
                     print(f"    >>> Creating NEW UNLINKED Finanças record for Guide CPSA {cpsa_id} (due to missing guide date/paciente).")
                     new_financa = ProcedimentoFinancas(
                         procedimento=None, group=group, tipo_cobranca='cooperativa', cpsa=cpsa_id,
                         #...(populate other fields from guia)...
                         valor_faturado=guia.get('valor_faturado'),
                         valor_recebido=guia.get('valor_recebido'),
                         valor_recuperado=guia.get('valor_receuperado'),
                         valor_acatado=guia.get('valor_acatado'),
                         status_pagamento=map_api_status(guia.get('STATUS')),
                         api_paciente_nome=guia.get('paciente'),
                         api_data_cirurgia=parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa'))),
                         api_hospital_nome=guia.get('hospital'),
                         api_cooperado_nome=guia.get('cooperado')
                     )
                     financas_to_create.append(new_financa)
                     newly_created_count += 1


        # --- Perform DB Operations ---
        if financas_to_update:
             print(f"--- Saving {len(financas_to_update)} updates ---")
             # Identify fields to update - include 'procedimento' and 'cpsa' as they might change
             update_fields = [
                'valor_faturado', 'valor_recebido', 'valor_recuperado', 'valor_acatado',
                'status_pagamento', 'procedimento', 'cpsa',
                'api_paciente_nome', 'api_data_cirurgia', 'api_hospital_nome', 'api_cooperado_nome'
             ]
             # Use bulk_update if possible, otherwise save individually
             # Note: bulk_update might be tricky if updating relations or unique fields that conflict temporarily
             # Saving individually might be safer here.
             for item in financas_to_update:
                  item.save()
             # ProcedimentoFinancas.objects.bulk_update(financas_to_update, update_fields) # Revisit if performance is an issue

        if financas_to_create:
            print(f"--- Creating {len(financas_to_create)} new records ---")
            ProcedimentoFinancas.objects.bulk_create(financas_to_create)

        # --- Final Reporting ---
        unprocessed_api_cpsa_ids = set(guias_dict.keys()) - processed_cpsa_ids # Should be empty now if logic covers all cases
        print(f"--- Conciliation Finished. Updated: {updated_records_count}, Created: {newly_created_count}, Linked: {newly_linked_count}, Unprocessed API CPSA: {len(unprocessed_api_cpsa_ids)} ---")
        if unprocessed_api_cpsa_ids: # Should ideally not happen with the revised logic
            print(f"Warning: {len(unprocessed_api_cpsa_ids)} CPSA IDs from API were not processed: {list(unprocessed_api_cpsa_ids)}")
            api_errors.append(f"{len(unprocessed_api_cpsa_ids)} guias da API não foram processadas.")

        # Construct summary message... (same as before)
        summary_message = []
        if updated_records_count > 0: summary_message.append(f"{updated_records_count} registros atualizados.")
        if newly_created_count > 0: summary_message.append(f"{newly_created_count} novos registros criados.")
        if newly_linked_count > 0: summary_message.append(f"{newly_linked_count} registros vinculados a procedimentos.")
        final_message = " ".join(summary_message) if summary_message else "Nenhuma alteração realizada."
        if api_errors: final_message += " " + " ".join(api_errors)

        return JsonResponse({
            'success': True, 'message': final_message,
            'updated_count': updated_records_count, 'created_count': newly_created_count,
            'linked_count': newly_linked_count,
            'unprocessed_cpsa_count': len(unprocessed_api_cpsa_ids),
            'unprocessed_cpsa_ids': list(unprocessed_api_cpsa_ids),
            'api_errors': api_errors
        })

    except requests.exceptions.RequestException as e:
        print(f"!!! API Request Exception: {str(e)}")
        return JsonResponse({'error': f'Erro na comunicação com a API: {str(e)}'}, status=500)
    except Exception as e:
        import traceback
        print(f"!!! Conciliation Exception: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': f'Erro interno durante a conciliação: {str(e)}'}, status=500)


