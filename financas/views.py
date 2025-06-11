from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from agenda.models import Procedimento, Convenios, ProcedimentoDetalhes
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED, CIRURGIA_PROCEDIMENTO, STATUS_PENDING
from registration.models import Groups, Membership, Anesthesiologist, HospitalClinic, Surgeon
from .models import ProcedimentoFinancas, Despesas, ConciliacaoTentativa
from django.db.models import Q, Sum, F, Value
from datetime import datetime, timedelta, time
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
import json
import pandas as pd
from django.http import HttpResponse
import requests
from difflib import SequenceMatcher
from django.conf import settings
from django.db import transaction

DATA_INICIO_PUXAR_GUIAS_API = datetime(2025, 4, 1).date()

@login_required
def financas_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    if request.user.user_type != GESTOR_USER:
        return HttpResponseForbidden("Acesso Negado")
    
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
        ).select_related('procedimento', 'procedimento__hospital').prefetch_related('procedimento__anestesistas_responsaveis')

        # Filter for user type
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
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
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'error': 'Acesso negado'}, status=403)

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
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
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
                group=user_group # Assuming only Gestor access despesas directly
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
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

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
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
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
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

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
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401) 
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

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
    if request.user.user_type != GESTOR_USER:
        return HttpResponseForbidden("Acesso Negado")

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
        ).select_related('procedimento', 'procedimento__hospital', 'procedimento__convenio').prefetch_related('procedimento__anestesistas_responsaveis')
        
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
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
            anest_name_list = []
            if item.procedimento and item.procedimento.anestesistas_responsaveis.exists():
                anest_name_list = [anest.name for anest in item.procedimento.anestesistas_responsaveis.all() if anest.name]
            
            anest_name = ", ".join(anest_name_list) if anest_name_list else (item.api_cooperado_nome or '')

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
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
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
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

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
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
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

def parse_api_time(time_str):
    """Safely parses time string from API format HH:MM."""
    if not time_str:
        return None
    try:
        # Handle various time formats (HH:MM, H:MM, etc.)
        time_str = str(time_str).strip()
        if ':' in time_str:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            return time(hour=hour, minute=minute)
        else:
            # Handle cases where only hour is provided
            hour = int(time_str)
            return time(hour=hour, minute=0)
    except (ValueError, TypeError):
        print(f"Warning: Could not parse time '{time_str}'")
        return None

def find_or_create_surgeon(group, surgeon_name, surgeon_crm=None):
    """Find existing surgeon or create new one based on name and CRM."""
    if not surgeon_name or not surgeon_name.strip():
        return None
    
    surgeon_name = surgeon_name.strip()
    surgeon_crm = surgeon_crm.strip() if surgeon_crm else None
    
    # Try to find existing surgeon by CRM first (if provided)
    if surgeon_crm:
        try:
            surgeon = Surgeon.objects.get(group=group, crm=surgeon_crm)
            print(f"        Found existing Surgeon by CRM: {surgeon.name} (CRM: {surgeon.crm})")
            return surgeon
        except Surgeon.DoesNotExist:
            pass
    
    # Try to find by name similarity
    surgeons_in_group = Surgeon.objects.filter(group=group)
    best_match_surgeon = None
    highest_sim = 0.7
    
    for surgeon in surgeons_in_group:
        if surgeon.name:
            sim_score = similar(surgeon_name, surgeon.name)
            if sim_score > highest_sim:
                highest_sim = sim_score
                best_match_surgeon = surgeon
    
    if best_match_surgeon:
        print(f"        Found matching Surgeon by name: {best_match_surgeon.name} (Sim: {highest_sim:.2f})")
        return best_match_surgeon
    
    # Create new surgeon
    new_surgeon = Surgeon.objects.create(
        name=surgeon_name,
        crm=surgeon_crm,
        group=group
    )
    print(f"        Created new Surgeon: {new_surgeon.name} (CRM: {new_surgeon.crm or 'N/A'})")
    return new_surgeon

def update_procedimento_with_api_data(procedimento, guia, group):
    """Update existing Procedimento with API data if it's more complete."""
    updated = False
    
    # Update times if API has them and they're more precise
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_hora_final = parse_api_time(guia.get('hora_final'))
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    
    if guia_date and guia_hora_inicial:
        new_data_horario = datetime.combine(guia_date, guia_hora_inicial)
        new_data_horario = timezone.make_aware(new_data_horario) if timezone.is_naive(new_data_horario) else new_data_horario
        
        current_time = procedimento.data_horario.time() if procedimento.data_horario else None
        if not current_time or current_time == time(0, 0) or current_time != guia_hora_inicial:
            procedimento.data_horario = new_data_horario
            updated = True
            print(f"        Updated Procedimento data_horario to {new_data_horario}")
    
    if guia_date and guia_hora_final:
        if guia_hora_final != guia_hora_inicial:
            new_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            new_data_horario_fim = timezone.make_aware(new_data_horario_fim) if timezone.is_naive(new_data_horario_fim) else new_data_horario_fim
            
            if not procedimento.data_horario_fim or procedimento.data_horario_fim != new_data_horario_fim:
                procedimento.data_horario_fim = new_data_horario_fim
                updated = True
                print(f"        Updated Procedimento data_horario_fim to {new_data_horario_fim}")
        else:
            print(f"        Skipping data_horario_fim update: API start and end times are the same ({guia_hora_inicial})")
    elif guia_date and guia_hora_inicial and not guia_hora_final:
        print(f"        API has no hora_final, keeping existing data_horario_fim")
    
    api_surgeon_name = guia.get('cirurgiao')
    api_surgeon_crm = guia.get('crm_cirurgiao')
    
    if api_surgeon_name and api_surgeon_name.strip():
        api_surgeon = find_or_create_surgeon(group, api_surgeon_name, api_surgeon_crm)
        if api_surgeon and (not procedimento.cirurgiao or procedimento.cirurgiao.id != api_surgeon.id):
            procedimento.cirurgiao = api_surgeon
            updated = True
            print(f"        Updated Procedimento surgeon to {api_surgeon.name}")
    
    api_hospital_name = guia.get('hospital')
    if api_hospital_name and api_hospital_name.strip():
        hospital_obj, created = HospitalClinic.objects.get_or_create(
            name__iexact=api_hospital_name.strip(),
            defaults={'name': api_hospital_name.strip(), 'group': group}
        )
        if not procedimento.hospital or procedimento.hospital.id != hospital_obj.id:
            procedimento.hospital = hospital_obj
            updated = True
            print(f"        Updated Procedimento hospital to {hospital_obj.name}")

    # Update ProcedimentoDetalhes (procedimento_principal)
    api_procedimentos = guia.get('procedimentos')
    if api_procedimentos and isinstance(api_procedimentos, list) and len(api_procedimentos) > 0:
        principal_proc_data = api_procedimentos[0] # Taking the first procedure as the principal
        api_codigo = principal_proc_data.get('codigo')
        api_descricao = principal_proc_data.get('descricao')

        if api_codigo and api_descricao:
            proc_detalhe, created = ProcedimentoDetalhes.objects.get_or_create(
                codigo_procedimento=api_codigo,
                defaults={'name': api_descricao}
            )
            if created:
                print(f"        Created new ProcedimentoDetalhes: {proc_detalhe.name} ({proc_detalhe.codigo_procedimento})")
            else:
                # Optionally update name if it differs, though codigo_procedimento is unique
                if proc_detalhe.name != api_descricao:
                    proc_detalhe.name = api_descricao
                    # proc_detalhe.save() # Decide if overriding name is desired
                    print(f"        Found existing ProcedimentoDetalhes, name updated if different: {proc_detalhe.name}")
                else:
                    print(f"        Found existing ProcedimentoDetalhes: {proc_detalhe.name}")

            if procedimento.procedimento_principal != proc_detalhe:
                procedimento.procedimento_principal = proc_detalhe
                updated = True
                print(f"        Updated Procedimento.procedimento_principal to {proc_detalhe.name}")
    
    if updated:
        procedimento.save()
        print(f"        Saved updates to Procedimento ID {procedimento.id}")
    
    return updated

def find_comprehensive_procedure_match(all_procs_list, guia, group):
    """
    Find existing Procedimento that matches all key fields from the guide.
    This prevents creating duplicate procedures for the same surgery with multiple financial charges.
    """
    guia_paciente = guia.get('paciente')
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_cooperado = guia.get('cooperado')
    guia_hospital = guia.get('hospital')
    guia_cirurgiao = guia.get('cirurgiao')
    
    # print(f"    🔍 COMPREHENSIVE MATCH DEBUG for CPSA {guia.get('idcpsa')}:")
    # print(f"      API Guide Data:")
    # print(f"        - Patient: '{guia_paciente}'")
    # print(f"        - Date: {guia_date}")
    # print(f"        - Time: {guia_hora_inicial}")
    # print(f"        - Cooperado: '{guia_cooperado}'")
    # print(f"        - Hospital: '{guia_hospital}'")
    # print(f"        - Surgeon: '{guia_cirurgiao}'")
    
    if not guia_paciente or not guia_date:
        # print(f"      ❌ SKIPPING: Missing essential data (patient: {bool(guia_paciente)}, date: {bool(guia_date)})")
        return None
    
    best_match_proc = None
    highest_score = 0.0
    
    # print(f"      📋 Checking {len(all_procs_list)} existing procedures...")
    
    for i, proc in enumerate(all_procs_list):
        # print(f"      [{i+1}/{len(all_procs_list)}] Checking Proc ID {proc.id}:")
        # print(f"        - Patient: '{proc.nome_paciente}'")
        # print(f"        - DateTime: {proc.data_horario}")
        # print(f"        - Hospital: {proc.hospital.name if proc.hospital else 'None'}")
        
        score = 0.0
        total_factors = 0
        
        # 1. Patient name similarity (most important) - CASE INSENSITIVE
        if proc.nome_paciente:
            name_sim = similar(guia_paciente.lower(), proc.nome_paciente.lower())
            # print(f"        - Name similarity: {name_sim:.3f}")
            if name_sim < 0.8:  # Skip if name similarity is too low
                # print(f"        ❌ SKIPPED: Name similarity too low ({name_sim:.3f} < 0.8)")
                continue
            score += name_sim * 0.4  # 40% weight
            total_factors += 0.4
            # print(f"        ✅ Name match: {name_sim:.3f} * 0.4 = {name_sim * 0.4:.3f}")
        
        # 2. Date match (essential)
        proc_date = proc.data_horario.date() if proc.data_horario else None
        if proc_date:
            date_diff = abs((guia_date - proc_date).days)
            # print(f"        - Date comparison: API {guia_date} vs Proc {proc_date} (diff: {date_diff} days)")
            if date_diff > 1:  # Skip if date difference is more than 1 day
                # print(f"        ❌ SKIPPED: Date difference too large ({date_diff} > 1 day)")
                continue
            date_score = 1.0 if date_diff == 0 else 0.7  # Exact date match gets full score
            score += date_score * 0.25  # 25% weight
            total_factors += 0.25
            # print(f"        ✅ Date match: {date_score} * 0.25 = {date_score * 0.25:.3f}")
        
        # 3. Time match (if available)
        if guia_hora_inicial and proc.data_horario:
            # Convert procedure's UTC time to local time for comparison
            proc_local_time = timezone.localtime(proc.data_horario).time()
            # print(f"        - Time comparison: API {guia_hora_inicial} vs Proc {proc_local_time} (converted from UTC)")
            if proc_local_time != time(0, 0):  # Only compare if procedure has a real time (not midnight default)
                time_diff_minutes = abs(
                    (guia_hora_inicial.hour * 60 + guia_hora_inicial.minute) - 
                    (proc_local_time.hour * 60 + proc_local_time.minute)
                )
                # print(f"        - Time difference: {time_diff_minutes} minutes")
                if time_diff_minutes <= 30:  # Within 30 minutes
                    time_score = 1.0 if time_diff_minutes == 0 else 0.8
                    score += time_score * 0.15  # 15% weight
                    total_factors += 0.15
                    # print(f"        ✅ Time match: {time_score} * 0.15 = {time_score * 0.15:.3f}")
                elif time_diff_minutes > 240:  # More than 4 hours difference
                    # print(f"        ❌ SKIPPED: Time difference too large ({time_diff_minutes} > 240 minutes)")
                    continue  # Skip this procedure
                else:
                    # print(f"        ⚠️ Time difference acceptable but not scored ({time_diff_minutes} minutes)")
                    pass
            else:
                # print(f"        ⚠️ Procedure has default midnight time, skipping time comparison")
                pass
        else:
            # print(f"        ⚠️ No time comparison possible (API time: {guia_hora_inicial}, Proc time: {proc.data_horario})")
            pass
        
        # 4. Hospital match (if available) - CASE INSENSITIVE
        if guia_hospital and proc.hospital:
            hospital_sim = similar(guia_hospital.lower(), proc.hospital.name.lower())
            # print(f"        - Hospital similarity: {hospital_sim:.3f}")
            if hospital_sim > 0.7:
                score += hospital_sim * 0.1  # 10% weight
                total_factors += 0.1
                # print(f"        ✅ Hospital match: {hospital_sim:.3f} * 0.1 = {hospital_sim * 0.1:.3f}")
            else:
                # print(f"        ⚠️ Hospital similarity too low ({hospital_sim:.3f} <= 0.7)")
                pass
        else:
            # print(f"        ⚠️ No hospital comparison possible")
            pass
        
        # 5. Anesthesiologist match (if available) - CASE INSENSITIVE
        if guia_cooperado and proc.anestesistas_responsaveis.exists():
            anest_match = False
            anest_names = [anest.name for anest in proc.anestesistas_responsaveis.all() if anest.name]
            # print(f"        - Anesthesiologist comparison: API '{guia_cooperado}' vs Proc {anest_names}")
            for anest in proc.anestesistas_responsaveis.all():
                if anest.name and similar(guia_cooperado.lower(), anest.name.lower()) > 0.8:
                    anest_match = True
                    # print(f"        ✅ Anesthesiologist match found: {anest.name}")
                    break
            if anest_match:
                score += 0.1  # 10% weight
                total_factors += 0.1
                # print(f"        ✅ Anesthesiologist match: 0.1")
            else:
                # print(f"        ⚠️ No anesthesiologist match found")
                pass
        else:
            # print(f"        ⚠️ No anesthesiologist comparison possible")
            pass
        
        # Calculate final score as percentage
        if total_factors > 0:
            final_score = score / total_factors
            # print(f"        📊 Final score: {score:.3f} / {total_factors:.3f} = {final_score:.3f}")
            
            # Require minimum combined score for match
            if final_score > 0.85 and final_score > highest_score:
                highest_score = final_score
                best_match_proc = proc
                # print(f"        🎯 NEW BEST MATCH! Score: {final_score:.3f}")
            elif final_score > 0.85:
                # print(f"        ✅ Good match but not better than current best ({highest_score:.3f})")
                pass
            else:
                # print(f"        ❌ Score too low ({final_score:.3f} <= 0.85)")
                pass
        else:
            # print(f"        ❌ No factors to compare (total_factors = 0)")
            pass
        # print(f"        ---")
    
    if best_match_proc:
        # print(f"      🎯 FINAL RESULT: Found match - Proc ID {best_match_proc.id} with score {highest_score:.3f}")
        pass
    else:
        # print(f"      ❌ FINAL RESULT: No comprehensive match found")
        pass
    
    return best_match_proc

@login_required
def conciliar_financas(request):
    if not request.user.validado:
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)
    if request.user.user_type != GESTOR_USER:
        return JsonResponse({'error': 'Acesso negado'}, status=403)

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
        #api_url = "https://aplicacao.coopanestrio.dev.br/portal/guias/ajaxGuias.php"  #TODO : endpoint dev para testes na parteb de procedimnto principal
        api_payload = {
            "conexao": user.connection_key,
            "periodo_de": DATA_INICIO_PUXAR_GUIAS_API.strftime('%Y-%m-%d'),
            "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
            "status": "Listagem Geral",
            "coopahub": "S"
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
        # print(f"API Fetch: Found {len(guias_dict)} guides with valid idcpsa.")

        # --- Fetch Existing DB Data ---
        # Fetch ALL relevant procedures for the group (within a reasonable timeframe?)
        # Let's keep fetching recent procedures for matching, but not filter by financas__isnull
        cutoff_date =  DATA_INICIO_PUXAR_GUIAS_API
        all_procs_qs = Procedimento.objects.filter(
            group=group,
            data_horario__date__gte=cutoff_date
        ).select_related('hospital', 'convenio').prefetch_related('financas_records') # Use prefetch_related for financas_records

        # Add anesthesiologist filter if applicable
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
            all_procs_qs = all_procs_qs.filter(anestesistas_responsaveis=user.anesthesiologist)
        
        all_procs_list = list(all_procs_qs)
        # print(f"DB Fetch: Found {len(all_procs_list)} potentially relevant procedures.")

        # Fetch existing financas records with CPSA (for quick lookup and updates)
        financas_qs = ProcedimentoFinancas.objects.filter(
            Q(procedimento__group=group) | Q(group=group),
            tipo_cobranca='cooperativa'
        ).select_related('procedimento') # Keep this select_related

        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
        if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
             financas_qs = financas_qs.filter(
                 Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                 Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
             )

        financas_dict_by_cpsa = {f.cpsa: f for f in financas_qs if f.cpsa}
        # print(f"DB Fetch: Found {len(financas_dict_by_cpsa)} existing financas records with CPSA.")

        # --- Processing ---
        financas_to_update = []
        financas_to_create = []
        processed_cpsa_ids = set()
        
        # Define batch size for processing
        BATCH_SIZE = 50
        
        # print("--- Processing API Guides ---")
        for cpsa_id, guia in guias_dict.items():
            # print(f"Processing Guide CPSA {cpsa_id} (Paciente: {guia.get('paciente')})")
            processed_cpsa_ids.add(cpsa_id) 
            
            guia_paciente = guia.get('paciente')
            guia_date_str = guia.get('dt_cirurg', guia.get('dt_cpsa'))
            guia_date = parse_api_date(guia_date_str)
            guia_cooperado = guia.get('cooperado') 

            if user.user_type == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                if not guia_cooperado or not similar(guia_cooperado.lower(), user.anesthesiologist.name.lower()) > 0.8:
                    # print(f"  Skipping CPSA {cpsa_id}: Cooperado mismatch for user {user.username}.")
                    continue

            if cpsa_id in financas_dict_by_cpsa:
                financa = financas_dict_by_cpsa[cpsa_id]
                # print(f"  Found existing Finanças ID {financa.id} with matching CPSA.")
                
                updated = False
                guia_valor_faturado = guia.get('valor_faturado')
                guia_valor_recebido = guia.get('valor_recebido')
                guia_valor_recuperado = guia.get('valor_receuperado', guia.get('valor_recuperado'))
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
                
                guia_api_date_parsed = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
                if financa.api_data_cirurgia != guia_api_date_parsed:
                    financa.api_data_cirurgia = guia_api_date_parsed; updated = True
                
                if updated:
                    # print(f"    Marked Finanças ID {financa.id} for update.")
                    if financa not in financas_to_update: financas_to_update.append(financa)
                
                if not financa.procedimento:
                     # print(f"    Existing Finanças ID {financa.id} is unlinked. Trying to find matching procedure...")
                     best_match_proc = None
                     highest_similarity = 0.7 
                     if guia_paciente and guia_date:
                          for proc in all_procs_list:
                              name_similarity = similar(guia_paciente.lower(), proc.nome_paciente.lower())
                              proc_date = proc.data_horario.date() if proc.data_horario else None
                              date_diff = abs((guia_date - proc_date).days) if proc_date else float('inf')
                              exact_match = name_similarity > 0.95 and date_diff == 0
                              good_match = name_similarity > 0.85 and date_diff <= 1
                              current_similarity = name_similarity
                              if (exact_match or good_match) and current_similarity > highest_similarity:
                                  highest_similarity = current_similarity
                                  best_match_proc = proc
                          if best_match_proc:
                              # Check if this procedure already has any financial records
                              existing_financas_for_proc = list(best_match_proc.financas_records.all())
                              
                              # Allow linking even if procedure has other financial records (multiple charges per procedure)
                              # print(f"    >>> Linking existing Finanças ID {financa.id} to Proc ID {best_match_proc.id} (Comprehensive match)")
                              
                              # Update the procedure with API data before linking
                              update_procedimento_with_api_data(best_match_proc, guia, group)
                              
                              financa.procedimento = best_match_proc
                              newly_linked_count += 1 
                              if financa not in financas_to_update: financas_to_update.append(financa)
                          else:
                               # print(f"    No suitable procedure found to link Finanças ID {financa.id} to.")
                               pass
                     else:
                         # print(f"    Cannot attempt linking Finanças ID {financa.id}: Guide missing patient/date.")
                         pass
                elif financa.procedimento:
                     processed_cpsa_ids.add(financa.cpsa)

            else: # No existing Finanças with this CPSA
                # print(f"  No existing Finanças with CPSA {cpsa_id}.")
                best_match_proc = None
                
                if guia_paciente and guia_date:
                    # print(f"    Searching for comprehensive Procedure match for Guide CPSA {cpsa_id} (Patient: {guia_paciente}, Date: {guia_date})...")
                    
                    # Use comprehensive matching instead of simple name/date matching
                    best_match_proc = find_comprehensive_procedure_match(all_procs_list, guia, group)
                    
                    if best_match_proc:
                        # print(f"      Found comprehensive Procedure match: Proc ID {best_match_proc.id}")
                        pass
                    else:
                        # print(f"      No comprehensive Procedure match found for Guide CPSA {cpsa_id}")
                        pass
                else:
                    # print(f"    Cannot attempt to find matching procedure for Guide CPSA {cpsa_id}: Guide missing patient/date.")
                    pass

                if best_match_proc: # Matching procedure found
                    # print(f"    Found matching Proc ID {best_match_proc.id}. Creating financial record for CPSA {cpsa_id}.")
                    
                    # Update the matched procedure with API data
                    update_procedimento_with_api_data(best_match_proc, guia, group)
                    
                    # print(f"    >>> Creating NEW Finanças record for Guide CPSA {cpsa_id} and linking to Proc ID {best_match_proc.id}.")
                    new_financa = ProcedimentoFinancas(
                        procedimento=best_match_proc,
                        group=group,
                        tipo_cobranca='cooperativa',
                        cpsa=cpsa_id,
                        valor_faturado=guia.get('valor_faturado'),
                        valor_recebido=guia.get('valor_recebido'),
                        valor_recuperado=guia.get('valor_receuperado', guia.get('valor_recuperado')),
                        valor_acatado=guia.get('valor_acatado'),
                        status_pagamento=map_api_status(guia.get('STATUS')),
                        api_paciente_nome=guia.get('paciente'),
                        api_data_cirurgia=guia_date, # Use parsed guia_date
                        api_hospital_nome=guia.get('hospital'),
                        api_cooperado_nome=guia.get('cooperado')
                    )
                    financas_to_create.append(new_financa)
                    newly_created_count += 1 # For ProcedimentoFinancas
                    newly_linked_count += 1
                else: # No matching procedure found OR guide data was insufficient to search
                    if guia_paciente and guia_date:
                        # print(f"    No matching Procedure found for Guide CPSA {cpsa_id} after search.")
                        
                        # Create new procedures in individual transactions
                        try:
                            with transaction.atomic():
                                newly_created_procedimento = create_new_procedimento_from_guia(guia, cpsa_id, group)
                                if newly_created_procedimento:
                                    all_procs_list.append(newly_created_procedimento)
                                    print(f"      Added new Procedimento ID {newly_created_procedimento.id} to search list for future matching.")
                        except Exception as e_proc_create:
                            print(f"    !!! Error creating new Procedimento for Guide CPSA {cpsa_id}: {str(e_proc_create)}")
                            import traceback
                            traceback.print_exc()
                            api_errors.append(f"Erro ao criar procedimento para guia {cpsa_id}: {str(e_proc_create)}")
                            newly_created_procedimento = None
                        
                        # print(f"    >>> Creating Finanças record for Guide CPSA {cpsa_id} (Linked to New Proc: {newly_created_procedimento.id if newly_created_procedimento else 'None'}).")
                        new_financa = ProcedimentoFinancas(
                             procedimento=newly_created_procedimento,
                             group=group,
                             tipo_cobranca='cooperativa',
                             cpsa=cpsa_id,
                             valor_faturado=guia.get('valor_faturado'),
                             valor_recebido=guia.get('valor_recebido'),
                             valor_recuperado=guia.get('valor_receuperado', guia.get('valor_recuperado')),
                             valor_acatado=guia.get('valor_acatado'),
                             status_pagamento=map_api_status(guia.get('STATUS')),
                             api_paciente_nome=guia.get('paciente'),
                             api_data_cirurgia=guia_date, # Use parsed guia_date
                             api_hospital_nome=guia.get('hospital'),
                             api_cooperado_nome=guia.get('cooperado')
                        )
                        financas_to_create.append(new_financa)
                        newly_created_count += 1 # For ProcedimentoFinancas
                        if newly_created_procedimento:
                            newly_linked_count += 1

            # Process updates in batches to prevent large transactions
            if len(financas_to_update) >= BATCH_SIZE:
                with transaction.atomic():
                    for item_to_update in financas_to_update:
                        item_to_update.save()
                    updated_records_count += len(financas_to_update)
                    print(f"--- Saved batch of {len(financas_to_update)} updates ---")
                financas_to_update = []

            # Process creates in batches to prevent large transactions
            if len(financas_to_create) >= BATCH_SIZE:
                with transaction.atomic():
                    ProcedimentoFinancas.objects.bulk_create(financas_to_create)
                    print(f"--- Created batch of {len(financas_to_create)} new records ---")
                financas_to_create = []

        # --- Perform Final DB Operations ---
        # Save any remaining updates
        if financas_to_update:
            with transaction.atomic():
                for item_to_update in financas_to_update:
                    item_to_update.save()
                updated_records_count += len(financas_to_update)
                print(f"--- Saved final batch of {len(financas_to_update)} updates ---")

        # Save any remaining creates
        if financas_to_create:
            with transaction.atomic():
                ProcedimentoFinancas.objects.bulk_create(financas_to_create)
                print(f"--- Created final batch of {len(financas_to_create)} new records ---")

        # --- Final Reporting ---
        unprocessed_api_cpsa_ids = set(guias_dict.keys()) - processed_cpsa_ids 
        print(f"--- Conciliation Finished. Updated: {updated_records_count}, Created: {newly_created_count}, Linked: {newly_linked_count}, Unprocessed API CPSA: {len(unprocessed_api_cpsa_ids)} ---")
        if unprocessed_api_cpsa_ids: 
            print(f"Warning: {len(unprocessed_api_cpsa_ids)} CPSA IDs from API were not processed: {list(unprocessed_api_cpsa_ids)}")
            api_errors.append(f"{len(unprocessed_api_cpsa_ids)} guias da API não foram processadas.")
        summary_message = []
        if updated_records_count > 0: summary_message.append(f"{updated_records_count} registros atualizados.")
        if newly_created_count > 0: summary_message.append(f"{newly_created_count} novos registros financeiros criados.")
        # Note: newly_linked_count now also includes links to newly created Procedimentos.
        # We could also add a counter for newly_created_procedimentos if needed for the summary.
        if newly_linked_count > 0: summary_message.append(f"{newly_linked_count} vínculos financeiros estabelecidos/atualizados com procedimentos.")

        final_message = " ".join(summary_message) if summary_message else "Nenhuma alteração financeira processada."
        if api_errors: final_message += " Erros: " + " ".join(api_errors)


        return JsonResponse({
            'success': True, 'message': final_message,
            'updated_count': updated_records_count, 'created_count': newly_created_count, # This is ProcedimentoFinancas created
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


def create_new_procedimento_from_guia(guia, cpsa_id, group):
    """
    Helper function to create a new Procedimento from API guide data.
    This is separated to allow individual transaction handling.
    """
    # print(f"    🚨 CREATING NEW PROCEDIMENTO for Guide CPSA {cpsa_id} (Patient: {guia.get('paciente')}, Date: {parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))}).")
    
    guia_paciente = guia.get('paciente')
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    
    # Parse API time information
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_hora_final = parse_api_time(guia.get('hora_final'))
    
    # Create datetime with time if available, otherwise use midnight
    proc_data_horario = None
    proc_data_horario_fim = None
    
    if guia_date:
        start_time = guia_hora_inicial if guia_hora_inicial else time(8, 0)  # Default to 8:00 AM
        proc_data_horario = datetime.combine(guia_date, start_time)
        proc_data_horario = timezone.make_aware(proc_data_horario) if timezone.is_naive(proc_data_horario) else proc_data_horario
        
        if guia_hora_final:
            proc_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            proc_data_horario_fim = timezone.make_aware(proc_data_horario_fim) if timezone.is_naive(proc_data_horario_fim) else proc_data_horario_fim
        else:
            # Default end time to start time + 2 hours
            proc_data_horario_fim = proc_data_horario + timedelta(hours=2)
    
    hospital_obj = None
    api_hospital_name = guia.get('hospital')
    if api_hospital_name and api_hospital_name.strip():
        hospital_obj, _ = HospitalClinic.objects.get_or_create(
            name__iexact=api_hospital_name.strip(),
            defaults={'name': api_hospital_name.strip(), 'group': group}
        )
    
    convenio_obj = None
    api_convenio_name = guia.get('convenio')
    if api_convenio_name and api_convenio_name.strip():
        convenio_obj, _ = Convenios.objects.get_or_create(
            name__iexact=api_convenio_name.strip(),
            defaults={'name': api_convenio_name.strip()}
        )

    # Find or create surgeon
    surgeon_obj = None
    api_surgeon_name = guia.get('cirurgiao')
    api_surgeon_crm = guia.get('crm_cirurgiao')
    if api_surgeon_name and api_surgeon_name.strip():
        surgeon_obj = find_or_create_surgeon(group, api_surgeon_name, api_surgeon_crm)

    paciente_nome_para_proc = guia_paciente
    if not paciente_nome_para_proc:
        paciente_nome_para_proc = f"Paciente Guia {cpsa_id}"
        # print(f"      Guia CPSA {cpsa_id} has no paciente name, using fallback: {paciente_nome_para_proc}")

    # Handle ProcedimentoDetalhes (procedimento_principal)
    procedimento_principal_obj = None
    api_procedimentos = guia.get('procedimentos')
    if api_procedimentos and isinstance(api_procedimentos, list) and len(api_procedimentos) > 0:
        principal_proc_data = api_procedimentos[0]
        api_codigo = principal_proc_data.get('codigo')
        api_descricao = principal_proc_data.get('descricao')
        if api_codigo and api_descricao:
            procedimento_principal_obj, created = ProcedimentoDetalhes.objects.get_or_create(
                codigo_procedimento=api_codigo,
                defaults={'name': api_descricao}
            )
            if created:
                print(f"        Created new ProcedimentoDetalhes for new Proc: {procedimento_principal_obj.name} ({procedimento_principal_obj.codigo_procedimento})")
            else:
                if procedimento_principal_obj.name != api_descricao:
                    procedimento_principal_obj.name = api_descricao
                    # procedimento_principal_obj.save() # Decide if overriding name is desired
                    print(f"        Found existing ProcedimentoDetalhes for new Proc, name updated if different: {procedimento_principal_obj.name}")
                else:
                    print(f"        Found existing ProcedimentoDetalhes for new Proc: {procedimento_principal_obj.name}")

    newly_created_procedimento = Procedimento.objects.create(
        group=group,
        nome_paciente=paciente_nome_para_proc,
        data_horario=proc_data_horario,
        data_horario_fim=proc_data_horario_fim,
        hospital=hospital_obj,
        convenio=convenio_obj,
        cirurgiao=surgeon_obj,
        procedimento_principal=procedimento_principal_obj, # Assign here
        procedimento_type=CIRURGIA_PROCEDIMENTO,
        status=STATUS_PENDING
    )
    print(f"      Created new Procedimento ID {newly_created_procedimento.id} for patient '{newly_created_procedimento.nome_paciente}' from guide CPSA {cpsa_id}")

    # Handle anesthesiologist
    guia_cooperado = guia.get('cooperado')
    if guia_cooperado:
        anest_user_qs = Anesthesiologist.objects.filter(group=group)
        best_match_anest = None
        highest_sim = 0.7
        for an_in_group in anest_user_qs:
            if an_in_group.name: # Ensure name is not empty for comparison
                sim_score = similar(guia_cooperado.lower(), an_in_group.name.lower())
                if sim_score > highest_sim:
                    highest_sim = sim_score
                    best_match_anest = an_in_group
        
        anest_final = None
        if best_match_anest:
            anest_final = best_match_anest
            print(f"        Found matching Anesthesiologist ID {anest_final.id} ({anest_final.name}) for cooperado '{guia_cooperado}'.")
        else:
            anest_final = Anesthesiologist.objects.create(
                name=guia_cooperado,
                group=group
            )
            print(f"        Created new Anesthesiologist ID {anest_final.id} ({anest_final.name}) for cooperado '{guia_cooperado}'.")
        
        if anest_final:
            newly_created_procedimento.anestesistas_responsaveis.add(anest_final)
            print(f"        Linked Anesthesiologist {anest_final.name} to new Procedimento {newly_created_procedimento.id}.")

    return newly_created_procedimento


