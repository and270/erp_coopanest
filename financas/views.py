from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from agenda.models import Procedimento, Convenios, ProcedimentoDetalhes
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED, STATUS_PENDING, CONSULTA_PROCEDIMENTO, CIRURGIA_AMBULATORIAL_PROCEDIMENTO
from registration.models import Groups, Membership, Anesthesiologist, HospitalClinic, Surgeon
from .models import ProcedimentoFinancas, Despesas, DespesasRecorrentes, ConciliacaoTentativa, ConciliacaoJob
import threading
from django.db.models import Q, Sum, F, Value
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime, timedelta, time
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.views.decorators.http import require_http_methods
import json
import pandas as pd
from django.http import HttpResponse
import requests
from difflib import SequenceMatcher
from django.conf import settings
from django.db import transaction
import re
from decimal import Decimal, InvalidOperation
import pytz

# Timezone de São Paulo - usar sempre este para processar horários do Brasil
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')

def make_aware_sao_paulo(dt):
    """
    Torna um datetime naive em datetime aware no fuso de São Paulo.
    Se já for aware, retorna sem alteração.
    """
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, SAO_PAULO_TZ)
    return dt

DATA_INICIO_PUXAR_GUIAS_API = datetime(2025, 1, 1).date()


def _get_conciliation_start_date(group, force_full=False):
    if force_full:
        return DATA_INICIO_PUXAR_GUIAS_API
    last_completed = (
        ConciliacaoJob.objects
        .filter(group=group, status='completed', completed_at__isnull=False)
        .order_by('-completed_at')
        .first()
    )
    buffer_candidates = []
    if last_completed and last_completed.completed_at:
        buffer_candidates.append((last_completed.completed_at - timedelta(days=7)).date())

    # Ensure we also cover any old guides still pending or in glosa
    pending_statuses = [
        'em_processamento',
        'aguardando_pagamento',
        'recurso_de_glosa',
    ]
    pending_qs = ProcedimentoFinancas.objects.filter(
        Q(group=group) | Q(procedimento__group=group),
        status_pagamento__in=pending_statuses,
    )
    oldest_pending_date = (
        pending_qs
        .exclude(procedimento__data_horario__isnull=True)
        .order_by('procedimento__data_horario')
        .values_list('procedimento__data_horario', flat=True)
        .first()
    )
    if oldest_pending_date:
        buffer_candidates.append((oldest_pending_date - timedelta(days=7)).date())

    oldest_pending_api_date = (
        pending_qs
        .exclude(api_data_cirurgia__isnull=True)
        .order_by('api_data_cirurgia')
        .values_list('api_data_cirurgia', flat=True)
        .first()
    )
    if oldest_pending_api_date:
        buffer_candidates.append((oldest_pending_api_date - timedelta(days=7)))

    if buffer_candidates:
        return max(DATA_INICIO_PUXAR_GUIAS_API, min(buffer_candidates))

    return DATA_INICIO_PUXAR_GUIAS_API


def clean_money_value(value_str):
    """
    Clean money string from mask format to decimal
    Example: "R$ 1.234,56" -> "1234.56"
    """
    if not value_str:
        return None
    
    # Remove currency symbol and spaces
    cleaned = str(value_str).replace('R$', '').strip()
    
    # Handle Brazilian format (1.234,56) -> American format (1234.56)
    if ',' in cleaned and '.' in cleaned:
        # Both comma and dot present - assume Brazilian format
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        # Only comma present - could be thousands separator or decimal
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Likely decimal separator
            cleaned = cleaned.replace(',', '.')
        else:
            # Likely thousands separator
            cleaned = cleaned.replace(',', '')
    
    # Remove any remaining non-numeric characters except decimal point
    cleaned = re.sub(r'[^\d.]', '', cleaned)
    
    try:
        return Decimal(cleaned) if cleaned else None
    except (InvalidOperation, ValueError):
        return None


def _api_decimal(value):
    """Convert API numeric (str/float/int/Decimal) to Decimal safely."""
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

@login_required
def financas_view(request):
    # Base permission check
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return redirect('home')  # Redirect non-gestores

    # Get user's group and other initial variables
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
        ).select_related('procedimento', 'procedimento__hospital', 'procedimento__cooperado').prefetch_related('procedimento__anestesistas_responsaveis')

        # Filter for user type
        active_role = user.get_active_role()
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
        if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
            base_qs = base_qs.filter(
                Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
            )
        elif active_role not in [GESTOR_USER, ADMIN_USER]: # Allow ADMIN too? Assume yes for now.
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
                Q(procedimento__cooperado__name__icontains=search_query) |
                Q(api_paciente_nome__icontains=search_query) |
                Q(api_cooperado_nome__icontains=search_query) |
                Q(matricula__icontains=search_query) |
                Q(senha__icontains=search_query)
            )

        # Apply status filter
        if status:
            base_qs = base_qs.filter(status_pagamento=status)

        # Order results
        queryset = base_qs.distinct().order_by(
            F('procedimento__data_horario').desc(nulls_last=True), # Prefer procedure date
            F('api_data_cirurgia').desc(nulls_last=True), # Fallback to API date
             '-id' # Final tie-breaker
        )

    else: # view_type == 'despesas'
        # Despesas logic remains largely unchanged, but ensure group filtering
        despesas_qs = Despesas.objects.filter(group=user_group).select_related('procedimento')
        despesas_recorrentes_qs = DespesasRecorrentes.objects.filter(group=user_group)

        # Filter for user type (Anesthesiologist might only see their own related expenses if logic requires)
        # Current logic shows all group expenses to Gestor/Admin, Anesthesiologist sees none directly unless linked?
        # Let's assume Gestor/Admin see all group expenses. Anesthesiologist logic might need review based on exact reqs.
        active_role = user.get_active_role()
        if active_role == ANESTESISTA_USER:
             # If Anesthesiologists should only see expenses linked to their procedures:
             # despesas_qs = despesas_qs.filter(procedimento__anestesistas_responsaveis=user.anesthesiologist)
             # If they see none, keep as is for now (or set to none())
             despesas_qs = Despesas.objects.none() # Assuming they don't see general expenses
             despesas_recorrentes_qs = DespesasRecorrentes.objects.none()
        elif active_role not in [GESTOR_USER, ADMIN_USER]:
             despesas_qs = Despesas.objects.none()
             despesas_recorrentes_qs = DespesasRecorrentes.objects.none()

        # Apply period filter
        if start_date and end_date:
            despesas_qs = despesas_qs.filter(data__gte=start_date, data__lte=end_date)
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(data_inicio__gte=start_date, data_inicio__lte=end_date)

        # Apply search filter
        if search_query:
            despesas_qs = despesas_qs.filter(descricao__icontains=search_query)
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(descricao__icontains=search_query)

        # Apply status filter (using 'pago' field for despesas, 'ativa' for recorrentes)
        if status == 'pago':
            despesas_qs = despesas_qs.filter(pago=True)
        elif status == 'nao_pago':
            despesas_qs = despesas_qs.filter(pago=False)
        elif status == 'ativa':
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(ativa=True)
        elif status == 'inativa':
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(ativa=False)

        # Order results
        despesas_list = list(despesas_qs.order_by('-data', '-id'))
        despesas_recorrentes_list = list(despesas_recorrentes_qs.order_by('-data_inicio', '-criado_em'))
        
        # Combine both lists and mark type for template
        for despesa in despesas_list:
            despesa.item_type = 'despesa'
        for despesa_rec in despesas_recorrentes_list:
            despesa_rec.item_type = 'despesa_recorrente'
        
        # Combine and sort by date (using data for despesas and data_inicio for recorrentes)
        queryset = sorted(
            despesas_list + despesas_recorrentes_list,
            key=lambda x: x.data if hasattr(x, 'data') else x.data_inicio,
            reverse=True
        )

    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(queryset, 50)  # Show 50 items per page
    try:
        items_page = paginator.page(page)
    except PageNotAnInteger:
        items_page = paginator.page(1)
    except EmptyPage:
        items_page = paginator.page(paginator.num_pages)

    context = {
        'items': items_page,
        'view_type': view_type,
        'selected_status': status,
        'search_query': search_query,
        'selected_period': selected_period,
        'custom_start_date': start_date_str,
        'custom_end_date': end_date_str,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'active_role': active_role,
        'user_group': user_group,
        'user_group_name': user_group.name if user_group else '',
    }

    return render(request, 'financas.html', context)

@login_required
def get_finance_item(request, type, id):
    if not request.user.validado:
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)
    
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
            active_role = user.get_active_role()
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'error': 'Acesso negado'}, status=403)
            elif active_role not in [GESTOR_USER, ADMIN_USER]:
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
                'matricula': item.matricula,
                'senha': item.senha,
                # Get data from procedure if linked, otherwise from api_* fields
                'paciente_nome': item.procedimento.nome_paciente if item.procedimento else item.api_paciente_nome,
                'cpf': item.procedimento.cpf_paciente if item.procedimento else None, # CPF only available if linked
                 'data_cirurgia': (item.procedimento.data_horario.strftime('%Y-%m-%d') if item.procedimento and item.procedimento.data_horario else 
                                  item.api_data_cirurgia.strftime('%Y-%m-%d') if item.api_data_cirurgia else None),
                 # New: expose cooperado and anestesistas livres for editing in modal (if needed later)
                 'cooperado': (item.procedimento.cooperado.name if item.procedimento and item.procedimento.cooperado else item.api_cooperado_nome),
                 'anestesistas_livres': (item.procedimento.anestesistas_livres if item.procedimento else ''),
                 # Add other fields as needed by the frontend modal
            }
        elif type == 'despesas':
            item = Despesas.objects.get(
                id=id,
                group=user_group # Assuming only Gestor access despesas directly
            )
             # Add specific permission checks for Despesas if needed
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'error': 'Acesso negado'}, status=403)
                 
            data = {
                'descricao': item.descricao,
                'valor': float(item.valor) if item.valor else 0,
                'data': item.data.strftime('%Y-%m-%d') if item.data else None,
                'pago': item.pago
            }
        else: # despesas_recorrentes
            item = DespesasRecorrentes.objects.get(
                id=id,
                group=user_group
            )
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'error': 'Acesso negado'}, status=403)
                 
            data = {
                'descricao': item.descricao,
                'valor': float(item.valor) if item.valor else 0,
                'periodicidade': item.periodicidade,
                'data_inicio': item.data_inicio.strftime('%Y-%m-%d') if item.data_inicio else None,
                'ativa': item.ativa
            }
        return JsonResponse(data)
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist, DespesasRecorrentes.DoesNotExist):
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
    
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
            active_role = user.get_active_role()
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)
            elif active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

            # Update common fields
            item.valor_faturado = clean_money_value(data.get('valor_faturado'))
            item.valor_recebido = clean_money_value(data.get('valor_recebido'))
            item.valor_recuperado = clean_money_value(data.get('valor_recuperado'))
            item.valor_acatado = clean_money_value(data.get('valor_acatado'))
            item.status_pagamento = data.get('status_pagamento')
            item.data_pagamento = data.get('data_pagamento') or None
            item.cpsa = data.get('cpsa') or None
            item.matricula = data.get('matricula') or None
            item.senha = data.get('senha') or None
            item.tipo_cobranca = data.get('tipo_cobranca')
            item.tipo_pagamento_direto = data.get('tipo_pagamento_direto') if data.get('tipo_cobranca') == 'particular' else None

            # Update procedure fields ONLY if linked
            if item.procedimento:
                item.procedimento.cpf_paciente = data.get('cpf') or None
                # Persist free-text anesthesiologists field from Finanças modal when linked
                anest_livres = data.get('anestesistas_livres')
                if anest_livres is not None:
                    item.procedimento.anestesistas_livres = anest_livres.strip()
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
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

            item.descricao = data.get('descricao')
            item.valor = clean_money_value(data.get('valor'))
            item.pago = data.get('pago') == 'on'
            item.data = data.get('data') or None

        elif finance_type == 'despesas_recorrentes':
            item = DespesasRecorrentes.objects.select_for_update().get(
                id=finance_id,
                group=user_group
            )
            # Permission check
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

            # Parse date
            data_inicio_str = data.get('data_inicio')
            try:
                data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Data de início inválida'}, status=400)

            item.descricao = data.get('descricao')
            item.valor = clean_money_value(data.get('valor'))
            item.periodicidade = data.get('periodicidade')
            item.data_inicio = data_inicio
            item.ativa = data.get('ativa') == 'on'

        else:
             return JsonResponse({'success': False, 'error': 'Tipo de item inválido'}, status=400)

        item.save()
        return JsonResponse({'success': True})
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist, DespesasRecorrentes.DoesNotExist):
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
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
            valor_faturado=clean_money_value(data.get('valor_faturado')),
            valor_recebido=clean_money_value(data.get('valor_recebido')),
            valor_recuperado=clean_money_value(data.get('valor_recuperado')),
            valor_acatado=clean_money_value(data.get('valor_acatado')),
            status_pagamento=status_pagamento,
            data_pagamento=data_pagamento,
            cpsa=cpsa or None,
            matricula=data.get('matricula') or None,
            senha=data.get('senha') or None,
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
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
            valor=clean_money_value(data.get('valor')), # Clean money value
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
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return HttpResponseForbidden("Acesso Negado")

    user = request.user
    user_group = user.group
    user_group_name = user_group.name if user_group else ''
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
        
        active_role = user.get_active_role()
        if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
             base_qs = base_qs.filter(
                 Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                 Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
             )
        elif active_role not in [GESTOR_USER, ADMIN_USER]:
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
                 Q(procedimento__anestesistas_responsaveis__name__icontains=search_query) |
                 Q(api_paciente_nome__icontains=search_query) |
                 Q(api_cooperado_nome__icontains=search_query) |
                 Q(matricula__icontains=search_query) |
                 Q(senha__icontains=search_query)
             ).distinct()
        if status:
             base_qs = base_qs.filter(status_pagamento=status)
        
        queryset = base_qs.distinct().order_by(
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

            # Convert datetimes to São Paulo timezone for correct export
            data_horario_local = None
            data_horario_fim_local = None
            if item.procedimento and item.procedimento.data_horario:
                data_horario_local = timezone.localtime(item.procedimento.data_horario, SAO_PAULO_TZ)
            if item.procedimento and item.procedimento.data_horario_fim:
                data_horario_fim_local = timezone.localtime(item.procedimento.data_horario_fim, SAO_PAULO_TZ)

            row = {
                'Paciente': item.procedimento.nome_paciente if item.procedimento else item.api_paciente_nome or '',
                'CPF': item.procedimento.cpf_paciente if item.procedimento else '',
                'Nascimento': item.procedimento.data_nascimento.strftime('%d/%m/%Y') if item.procedimento and item.procedimento.data_nascimento else '',
                'Data Cirurgia': (data_horario_local.strftime('%d/%m/%Y') if data_horario_local else 
                                  item.api_data_cirurgia.strftime('%d/%m/%Y') if item.api_data_cirurgia else ''),
                'Horário': (f"{data_horario_local.strftime('%H:%M')}" + (f" - {data_horario_fim_local.strftime('%H:%M')}" if data_horario_fim_local else "") if data_horario_local else ''),
                'Valor Faturado': float(item.valor_faturado) if item.valor_faturado is not None else 0.0,
                'Valor Recebido': float(item.valor_recebido) if item.valor_recebido is not None else 0.0,
                'Valor Recuperado': float(item.valor_recuperado) if item.valor_recuperado is not None else 0.0,
                'Valor a Recuperar': float(item.valor_acatado) if item.valor_acatado is not None else 0.0, # Glosa?
                'Fonte Pagadora': item.get_tipo_cobranca_display() or '',
                'CPSA': item.get_cpsa_display() or '',
                'Matrícula': item.matricula or '',
                'Senha': item.senha or '',
            }
            # Include Plantão/Eletiva column for Américas groups to match on-screen table
            if user_group_name in ('Américas', 'AMCRJ - SERVICOS MEDICOS LTDA'):
                row['Plantão/Eletiva'] = item.plantao_eletiva or ''
            
            row['Acomodação'] = item.procedimento.acomodacao if item.procedimento else ''

            # Continue with remaining columns
            row.update({
                'Anestesista': anest_name,
                'Cirurgião': (f"{item.procedimento.cirurgiao.name}" + (f" ({item.procedimento.cirurgiao.crm})" if item.procedimento.cirurgiao.crm else "") if item.procedimento and item.procedimento.cirurgiao else ''),
                'Situação': item.get_status_pagamento_display() or '',
                'Data do Pagamento': item.data_pagamento.strftime('%d/%m/%Y') if item.data_pagamento else '-',
                'Hospital': item.procedimento.hospital.name if item.procedimento and item.procedimento.hospital else item.api_hospital_nome or '',
                'Convênio': item.procedimento.convenio.name if item.procedimento and item.procedimento.convenio else '',
                'Vinculado': 'Sim' if item.procedimento else 'Não', # Indicate if linked
            })

            data.append(row)


    else: # view_type == 'despesas'
        # --- Replicate financas_view logic to fetch both Despesas and DespesasRecorrentes ---
        despesas_qs = Despesas.objects.filter(group=user_group)
        despesas_recorrentes_qs = DespesasRecorrentes.objects.filter(group=user_group)

        active_role = user.get_active_role()
        if active_role == ANESTESISTA_USER or active_role not in [GESTOR_USER, ADMIN_USER]:
            despesas_qs = Despesas.objects.none()
            despesas_recorrentes_qs = DespesasRecorrentes.objects.none()

        # Apply period filter
        if start_date and end_date:
            despesas_qs = despesas_qs.filter(data__gte=start_date, data__lte=end_date)
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(data_inicio__gte=start_date, data_inicio__lte=end_date)

        # Apply search filter
        if search_query:
            despesas_qs = despesas_qs.filter(descricao__icontains=search_query)
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(descricao__icontains=search_query)

        # Apply status filter exactly as in financas_view
        if status == 'pago':
            despesas_qs = despesas_qs.filter(pago=True)
        elif status == 'nao_pago':
            despesas_qs = despesas_qs.filter(pago=False)
        elif status == 'ativa':
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(ativa=True)
        elif status == 'inativa':
            despesas_recorrentes_qs = despesas_recorrentes_qs.filter(ativa=False)

        # Fetch, combine, and sort the items
        despesas_list = list(despesas_qs)
        despesas_recorrentes_list = list(despesas_recorrentes_qs)

        all_items = sorted(
            despesas_list + despesas_recorrentes_list,
            key=lambda x: x.data if hasattr(x, 'data') else x.data_inicio,
            reverse=True
        )

        # Prepare data for export
        data = []
        for item in all_items:
            if isinstance(item, Despesas):
                data.append({
                    'Tipo': 'Despesa Pontual',
                    'Descrição': item.descricao,
                    'Data': item.data.strftime('%d/%m/%Y') if item.data else '',
                    'Valor': float(item.valor) if item.valor is not None else 0.0,
                    'Status': 'Pago' if item.pago else 'Não Pago',
                    'Periodicidade': '-',
                })
            elif isinstance(item, DespesasRecorrentes):
                data.append({
                    'Tipo': 'Despesa Recorrente',
                    'Descrição': item.descricao,
                    'Data': item.data_inicio.strftime('%d/%m/%Y') if item.data_inicio else '',
                    'Valor': float(item.valor) if item.valor is not None else 0.0,
                    'Status': 'Ativa' if item.ativa else 'Inativa',
                    'Periodicidade': item.get_periodicidade_display(),
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
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
            active_role = user.get_active_role()
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                 is_linked_and_responsible = item.procedimento and item.procedimento.anestesistas_responsaveis.filter(id=user.anesthesiologist.id).exists()
                 is_unlinked_and_cooperado = not item.procedimento and item.api_cooperado_nome and similar(item.api_cooperado_nome.lower(), user.anesthesiologist.name.lower()) > 0.8
                 if not (is_linked_and_responsible or is_unlinked_and_cooperado):
                     return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)
            elif active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)

        elif finance_type == 'despesas':
            item = Despesas.objects.get(
                id=finance_id,
                group=user_group
            )
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)
        elif finance_type == 'despesas_recorrentes':
            item = DespesasRecorrentes.objects.get(
                id=finance_id,
                group=user_group
            )
            active_role = user.get_active_role()
            if active_role not in [GESTOR_USER, ADMIN_USER]:
                 return JsonResponse({'success': False, 'error': 'Acesso negado para excluir'}, status=403)
        else:
             return JsonResponse({'success': False, 'error': 'Tipo inválido'}, status=400)

        item.delete()
        return JsonResponse({'success': True})

    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist, DespesasRecorrentes.DoesNotExist):
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


def _sorted_guias_newest_first(guias_dict):
    def _guias_sort_key(item):
        _, guia = item
        guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
        guia_time = parse_api_time(guia.get('hora_inicial'))
        if guia_date:
            guia_time = guia_time or time(0, 0)
            return datetime.combine(guia_date, guia_time)
        return datetime.min

    return sorted(guias_dict.items(), key=_guias_sort_key, reverse=True)

def find_or_create_anesthesiologist(group, anesthesiologist_name):
    """Find existing anesthesiologist by similarity in the group or create a new one."""
    if not anesthesiologist_name or not str(anesthesiologist_name).strip():
        return None

    name = str(anesthesiologist_name).strip()
    # Try exact (case-insensitive) match first
    exact = Anesthesiologist.objects.filter(group=group, name__iexact=name).first()
    if exact:
        return exact

    best_match = None
    highest_sim = 0.7
    for candidate in Anesthesiologist.objects.filter(group=group):
        if candidate.name:
            sim_score = similar(name, candidate.name)
            if sim_score > highest_sim:
                highest_sim = sim_score
                best_match = candidate
    if best_match:
        return best_match

    # Create new when no good match found
    return Anesthesiologist.objects.create(name=name, group=group)

def find_or_create_surgeon(group, surgeon_name, surgeon_crm=None):
    """Find existing surgeon or create new one based on name and CRM."""
    if not surgeon_name or not surgeon_name.strip():
        return None
    
    surgeon_name = surgeon_name.strip()
    surgeon_crm = surgeon_crm.strip() if surgeon_crm else None
    
    # Try to find existing surgeon by CRM first (if provided)
    if surgeon_crm:
        surgeon = Surgeon.objects.filter(group=group, crm=surgeon_crm).first()
        if surgeon:
            return surgeon
    
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
        return best_match_surgeon
    
    # Create new surgeon
    new_surgeon = Surgeon.objects.create(
        name=surgeon_name,
        crm=surgeon_crm,
        group=group
    )
    return new_surgeon

def update_procedimento_with_api_data(procedimento, guia, group, save_immediately=True):
    """
    Update existing Procedimento with API data if it's more complete.
    If save_immediately is False, the caller must handle saving the procedimento.
    Returns (updated, procedimento) tuple - updated is True if any changes were made.
    """
    updated = False
    
    # Update times if API has them and they're more precise
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_hora_final = parse_api_time(guia.get('hora_final'))
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    
    if guia_date and guia_hora_inicial:
        new_data_horario = datetime.combine(guia_date, guia_hora_inicial)
        new_data_horario = make_aware_sao_paulo(new_data_horario)
        
        current_time = procedimento.data_horario.time() if procedimento.data_horario else None
        if not current_time or current_time == time(0, 0) or current_time != guia_hora_inicial:
            procedimento.data_horario = new_data_horario
            updated = True
    
    if guia_date and guia_hora_final:
        if guia_hora_final != guia_hora_inicial:
            new_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            new_data_horario_fim = make_aware_sao_paulo(new_data_horario_fim)
            
            if not procedimento.data_horario_fim or procedimento.data_horario_fim != new_data_horario_fim:
                procedimento.data_horario_fim = new_data_horario_fim
                updated = True

    # Update CPF if present and missing in procedure
    api_cpf = guia.get('cpf') or guia.get('nr_cpf')
    if api_cpf and not procedimento.cpf_paciente:
        procedimento.cpf_paciente = api_cpf
        updated = True

    # Update Data Nascimento if present and missing in procedure (API sends as 'data_nascimento')
    api_nascimento = parse_api_date(guia.get('data_nascimento'))
    if api_nascimento and not procedimento.data_nascimento:
        procedimento.data_nascimento = api_nascimento
        updated = True

    # Update Acomodação if present (API sends as 'tip_acomod')
    api_acomodacao = guia.get('tip_acomod')
    if api_acomodacao and not procedimento.acomodacao:
        procedimento.acomodacao = api_acomodacao
        updated = True
    
    api_surgeon_name = guia.get('cirurgiao')
    api_surgeon_crm = guia.get('crm_cirurgiao')
    
    if api_surgeon_name and api_surgeon_name.strip():
        api_surgeon = find_or_create_surgeon(group, api_surgeon_name, api_surgeon_crm)
        if api_surgeon and (not procedimento.cirurgiao or procedimento.cirurgiao.id != api_surgeon.id):
            procedimento.cirurgiao = api_surgeon
            updated = True
    
    api_hospital_name = guia.get('hospital')
    if api_hospital_name and api_hospital_name.strip():
        hospital_obj, created = HospitalClinic.objects.get_or_create(
            name__iexact=api_hospital_name.strip(),
            defaults={'name': api_hospital_name.strip(), 'group': group}
        )
        if not procedimento.hospital or procedimento.hospital.id != hospital_obj.id:
            procedimento.hospital = hospital_obj
            updated = True

    # Sync Cooperado on Procedimento from API 'cooperado'
    api_cooperado_name = guia.get('cooperado')
    if api_cooperado_name:
        anest = find_or_create_anesthesiologist(group, api_cooperado_name)
        if anest and (not procedimento.cooperado or procedimento.cooperado_id != anest.id):
            procedimento.cooperado = anest
            updated = True

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
            if not created:
                if proc_detalhe.name != api_descricao:
                    proc_detalhe.name = api_descricao
                    proc_detalhe.save() # Decide if overriding name is desired

            if procedimento.procedimento_principal != proc_detalhe:
                procedimento.procedimento_principal = proc_detalhe
                # Also update the procedure type based on the new principal procedure
                if proc_detalhe.codigo_procedimento == '10101012':
                    procedimento.procedimento_type = CONSULTA_PROCEDIMENTO
                else:
                    procedimento.procedimento_type = CIRURGIA_AMBULATORIAL_PROCEDIMENTO
                updated = True
    
    if updated and save_immediately:
        procedimento.save()
    
    return (updated, procedimento)

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
    
    if not guia_paciente or not guia_date:
        return None
    
    best_match_proc = None
    highest_score = 0.0
    
    for proc in all_procs_list:
        score = 0.0
        total_factors = 0
        
        # 1. Patient name similarity (most important) - CASE INSENSITIVE
        if proc.nome_paciente:
            name_sim = similar(guia_paciente.lower(), proc.nome_paciente.lower())
            if name_sim < 0.8:  # Skip if name similarity is too low
                continue
            score += name_sim * 0.4  # 40% weight
            total_factors += 0.4
        
        # 2. Date match (essential)
        proc_date = proc.data_horario.date() if proc.data_horario else None
        if proc_date:
            date_diff = abs((guia_date - proc_date).days)
            if date_diff > 1:  # Skip if date difference is more than 1 day
                continue
            date_score = 1.0 if date_diff == 0 else 0.7  # Exact date match gets full score
            score += date_score * 0.25  # 25% weight
            total_factors += 0.25
        
        # 3. Time match (if available)
        if guia_hora_inicial and proc.data_horario:
            # Convert procedure's UTC time to local time for comparison
            proc_local_time = timezone.localtime(proc.data_horario).time()
            if proc_local_time != time(0, 0):  # Only compare if procedure has a real time (not midnight default)
                time_diff_minutes = abs(
                    (guia_hora_inicial.hour * 60 + guia_hora_inicial.minute) - 
                    (proc_local_time.hour * 60 + proc_local_time.minute)
                )
                if time_diff_minutes <= 30:  # Within 30 minutes
                    time_score = 1.0 if time_diff_minutes == 0 else 0.8
                    score += time_score * 0.15  # 15% weight
                    total_factors += 0.15
                elif time_diff_minutes > 240:  # More than 4 hours difference
                    continue  # Skip this procedure
        
        # 4. Hospital match (if available) - CASE INSENSITIVE
        if guia_hospital and proc.hospital:
            hospital_sim = similar(guia_hospital.lower(), proc.hospital.name.lower())
            if hospital_sim > 0.7:
                score += hospital_sim * 0.1  # 10% weight
                total_factors += 0.1
        
        # 5. Anesthesiologist match (if available) - CASE INSENSITIVE
        if guia_cooperado and proc.anestesistas_responsaveis.exists():
            anest_match = False
            
            for anest in proc.anestesistas_responsaveis.all():
                if anest.name and similar(guia_cooperado.lower(), anest.name.lower()) > 0.8:
                    anest_match = True
                    break
            if anest_match:
                score += 0.1  # 10% weight
                total_factors += 0.1
        
        # Calculate final score as percentage
        if total_factors > 0:
            final_score = score / total_factors
            
            # Require minimum combined score for match
            if final_score > 0.85 and final_score > highest_score:
                highest_score = final_score
                best_match_proc = proc
    
    return best_match_proc

@login_required
def conciliar_financas(request):
    if not request.user.validado:
        # End the current session and instruct frontend to redirect to login
        logout(request)
        return JsonResponse({'error': 'Sessão expirada. Faça login novamente.', 'redirect_url': settings.LOGIN_URL}, status=401)
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
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
        fast = request.GET.get('fast') == '1'
        force_full = request.GET.get('full') == '1' or not fast
        start_date = _get_conciliation_start_date(group, force_full=force_full)
        api_payload = {
            "conexao": user.connection_key,
            "periodo_de": start_date.strftime('%Y-%m-%d'),
            "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
            "status": "Listagem Geral",
            "coopahub": "S"
        }
        response = requests.post(api_url, json=api_payload, timeout=120)
        response.raise_for_status()
        
        # Debug prints for raw API response (avoid heavy logging in production)
        if getattr(settings, 'DEBUG', False):
            print(f"=== RAW API RESPONSE DEBUG ===")
            print(f"Response Status Code: {response.status_code}")
            print(f"Raw Response Text (first 500 chars): {response.text[:500]}")
            print(f"=== END RAW API RESPONSE DEBUG ===")
        
        api_response_data = response.json()
        
        # Show example of a single guia for debugging (avoid heavy logging in production)
        if getattr(settings, 'DEBUG', False):
            guias_for_debug = api_response_data.get('listaguias', [])
            if guias_for_debug:
                print(f"=== SINGLE GUIA EXAMPLE ===")
                print(f"Example Guia JSON: {guias_for_debug[0]}")
                print(f"\n=== ALL KEYS AVAILABLE: ===")
                print(f"Keys: {list(guias_for_debug[0].keys())}")
                print(f"=== END SINGLE GUIA EXAMPLE ===")

        if api_response_data.get('erro') != '000':
            error_msg = f"API Error: {api_response_data.get('msg', 'Unknown API error')}"
            print(f"API Error for group {group.name}: {error_msg}")
            return JsonResponse({'error': error_msg}, status=500)

        guias = api_response_data.get('listaguias', [])
        
        
        # Filter out guides without essential nrocpsa
        guias_dict = {
            str(g['nrocpsa']): g for g in guias
            if g.get('nrocpsa') and str(g.get('nrocpsa')).strip()
        }
        print(f"API Fetch: Found {len(guias_dict)} guides with valid nrocpsa.")
        guias_items = _sorted_guias_newest_first(guias_dict)

        # --- Fetch Existing DB Data ---
        # Fetch existing financas records with CPSA (for quick lookup and updates)
        financas_qs = ProcedimentoFinancas.objects.filter(
            Q(procedimento__group=group) | Q(group=group)
        ).select_related('procedimento') # Keep this select_related

        active_role = user.get_active_role()
        #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
        if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
             financas_qs = financas_qs.filter(
                 Q(procedimento__anestesistas_responsaveis=user.anesthesiologist) |
                 Q(procedimento__isnull=True, api_cooperado_nome__iexact=user.anesthesiologist.name)
             )

        financas_dict_by_cpsa = {f.cpsa: f for f in financas_qs if f.cpsa}
        print(f"DB Fetch: Found {len(financas_dict_by_cpsa)} existing financas records with CPSA.")

        guias_cpsa_ids = set(guias_dict.keys())
        missing_cpsa_ids = guias_cpsa_ids - set(financas_dict_by_cpsa.keys())
        unlinked_financas_exists = financas_qs.filter(procedimento__isnull=True).exists()
        needs_procedure_matching = bool(missing_cpsa_ids) or unlinked_financas_exists

        from collections import defaultdict
        all_procs_list = []
        proc_lookup_dict = defaultdict(list)
        hospital_cache = {}
        convenio_cache = {}
        surgeon_cache = {}
        anesthesiologist_cache = {}
        proc_detalhes_cache = {}

        if needs_procedure_matching:
            # Fetch ALL relevant procedures for the group (within a reasonable timeframe?)
            # Let's keep fetching recent procedures for matching, but not filter by financas__isnull
            cutoff_date = start_date
            all_procs_qs = Procedimento.objects.filter(
                group=group,
                data_horario__date__gte=cutoff_date
            ).select_related('hospital', 'convenio').prefetch_related('financas_records') # Use prefetch_related for financas_records

            # Add anesthesiologist filter if applicable
            active_role = user.get_active_role()
            #Apesar de anestesista não terem acesso a parte de financas, assegurado pela validação acima, deixamos essa parte caso futuramnete venham a ter e então verão apenas a sua parte
            if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                all_procs_qs = all_procs_qs.filter(anestesistas_responsaveis=user.anesthesiologist)
            
            all_procs_list = list(all_procs_qs)
            print(f"DB Fetch: Found {len(all_procs_list)} potentially relevant procedures.")

            # --- Build O(1) lookup dictionary for procedures by (patient_name_lower, date) ---
            # This avoids O(n) iteration for each guide
            for proc in all_procs_list:
                if proc.nome_paciente and proc.data_horario:
                    key = (proc.nome_paciente.strip().lower(), proc.data_horario.date())
                    proc_lookup_dict[key].append(proc)
            print(f"Built procedure lookup with {len(proc_lookup_dict)} unique (patient, date) keys.")

            # --- Build caches for related entities to avoid repeated get_or_create queries ---
            # Cache hospitals by name (lowercase)
            hospital_cache = {h.name.lower(): h for h in HospitalClinic.objects.filter(group=group)}
            # Cache convenios by name (lowercase)
            convenio_cache = {c.name.lower(): c for c in Convenios.objects.all()}
            # Cache surgeons by name (lowercase)
            surgeon_cache = {s.name.lower(): s for s in Surgeon.objects.filter(group=group) if s.name}
            # Cache anesthesiologists by name (lowercase)
            anesthesiologist_cache = {a.name.lower(): a for a in Anesthesiologist.objects.filter(group=group) if a.name}
            # Cache procedimento detalhes by codigo
            proc_detalhes_cache = {pd.codigo_procedimento: pd for pd in ProcedimentoDetalhes.objects.all() if pd.codigo_procedimento}
            print(f"Built entity caches: {len(hospital_cache)} hospitals, {len(convenio_cache)} convenios, {len(surgeon_cache)} surgeons, {len(anesthesiologist_cache)} anesthesiologists, {len(proc_detalhes_cache)} proc_detalhes.")
        else:
            print("Skipping procedure/caches: no missing CPSA and no unlinked financas.")

        # --- Processing ---
        financas_to_update = []
        financas_to_create = []
        procedimentos_to_update = {}  # Dict by id to avoid duplicates
        procedimentos_to_create = []  # List of (Procedimento, guia, cpsa_id) tuples for bulk_create
        financas_pending_proc = []    # List of (financa_data, proc_index) for linking after bulk_create
        processed_cpsa_ids = set()
        
        # Define batch size for processing - increased for better performance
        BATCH_SIZE = 200
        
        # Fields to update for bulk_update
        FINANCAS_UPDATE_FIELDS = [
            'valor_faturado', 'valor_recebido', 'valor_recuperado', 'valor_acatado',
            'status_pagamento', 'api_paciente_nome', 'api_hospital_nome', 'api_cooperado_nome',
            'matricula', 'senha', 'api_data_cirurgia', 'plantao_eletiva', 'procedimento'
        ]
        PROCEDIMENTO_UPDATE_FIELDS = [
            'data_horario', 'data_horario_fim', 'cpf_paciente', 'data_nascimento',
            'acomodacao', 'cirurgiao', 'hospital', 'cooperado', 'procedimento_principal', 'procedimento_type'
        ]
        
        print("--- Processing API Guides ---")
        for cpsa_id, guia in guias_items:
            processed_cpsa_ids.add(cpsa_id) 
            
            guia_paciente = guia.get('paciente')
            guia_date_str = guia.get('dt_cirurg', guia.get('dt_cpsa'))
            guia_date = parse_api_date(guia_date_str)
            guia_cooperado = guia.get('cooperado') 

            active_role = user.get_active_role()
            if active_role == ANESTESISTA_USER and hasattr(user, 'anesthesiologist'):
                if not guia_cooperado or not similar(guia_cooperado.lower(), user.anesthesiologist.name.lower()) > 0.8:
                    continue

            if cpsa_id in financas_dict_by_cpsa:
                financa = financas_dict_by_cpsa[cpsa_id]
                
                if financa.tipo_cobranca == 'cooperativa':
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
                    if financa.matricula != guia.get('matricula'):
                        financa.matricula = guia.get('matricula'); updated = True
                    if financa.senha != guia.get('senha'):
                        financa.senha = guia.get('senha'); updated = True
                    
                    guia_api_date_parsed = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
                    if financa.api_data_cirurgia != guia_api_date_parsed:
                        financa.api_data_cirurgia = guia_api_date_parsed; updated = True
                    
                    if financa.plantao_eletiva != guia.get('classificacao'):
                        financa.plantao_eletiva = guia.get('classificacao'); updated = True
                    
                    if updated:
                        if financa not in financas_to_update: financas_to_update.append(financa)

                if not financa.procedimento and needs_procedure_matching:
                     best_match_proc = None
                     highest_similarity = 0.7 
                     if guia_paciente and guia_date:
                          # Use O(1) lookup first
                          lookup_key = (guia_paciente.strip().lower(), guia_date)
                          candidate_procs = proc_lookup_dict.get(lookup_key, [])
                          
                          # If no exact match, try adjacent dates
                          if not candidate_procs:
                              next_day = guia_date + timedelta(days=1)
                              prev_day = guia_date - timedelta(days=1)
                              candidate_procs = (
                                  proc_lookup_dict.get((guia_paciente.strip().lower(), next_day), []) +
                                  proc_lookup_dict.get((guia_paciente.strip().lower(), prev_day), [])
                              )
                          
                          # If still no match, fall back to similarity search (limited)
                          if not candidate_procs and len(all_procs_list) <= 100:
                              candidate_procs = all_procs_list
                          
                          for proc in candidate_procs:
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
                              # Update the procedure with API data before linking
                              update_procedimento_with_api_data(best_match_proc, guia, group)
                              
                              financa.procedimento = best_match_proc
                              newly_linked_count += 1 
                              if financa not in financas_to_update: financas_to_update.append(financa)
                elif financa.procedimento:
                     # Also update existing linked procedures (deferred save for bulk_update)
                     was_updated, updated_proc = update_procedimento_with_api_data(financa.procedimento, guia, group, save_immediately=False)
                     if was_updated:
                         procedimentos_to_update[updated_proc.id] = updated_proc
                     processed_cpsa_ids.add(financa.cpsa)

            else: # No existing Finanças with this CPSA
                best_match_proc = None
                
                if guia_paciente and guia_date:
                    # Use comprehensive matching instead of simple name/date matching
                    best_match_proc = find_comprehensive_procedure_match(all_procs_list, guia, group)

                if best_match_proc: # Matching procedure found
                    # Update the matched procedure with API data (deferred save)
                    was_updated, updated_proc = update_procedimento_with_api_data(best_match_proc, guia, group, save_immediately=False)
                    if was_updated:
                        procedimentos_to_update[updated_proc.id] = updated_proc
                    
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
                        api_cooperado_nome=guia.get('cooperado'),
                        matricula=guia.get('matricula'),
                        senha=guia.get('senha'),
                        plantao_eletiva=guia.get('classificacao')
                    )
                    financas_to_create.append(new_financa)
                    newly_created_count += 1 # For ProcedimentoFinancas
                    newly_linked_count += 1
                else: # No matching procedure found OR guide data was insufficient to search
                    if guia_paciente and guia_date:
                        # Prepare procedure object without saving (for bulk_create)
                        try:
                            proc_obj = prepare_procedimento_from_guia(
                                guia, cpsa_id, group,
                                hospital_cache, convenio_cache, surgeon_cache,
                                anesthesiologist_cache, proc_detalhes_cache
                            )
                            if proc_obj:
                                procedimentos_to_create.append(proc_obj)
                                # Store financa data with index to link after bulk_create
                                financa_data = {
                                    'group': group,
                                    'tipo_cobranca': 'cooperativa',
                                    'cpsa': cpsa_id,
                                    'valor_faturado': guia.get('valor_faturado'),
                                    'valor_recebido': guia.get('valor_recebido'),
                                    'valor_recuperado': guia.get('valor_receuperado', guia.get('valor_recuperado')),
                                    'valor_acatado': guia.get('valor_acatado'),
                                    'status_pagamento': map_api_status(guia.get('STATUS')),
                                    'api_paciente_nome': guia.get('paciente'),
                                    'api_data_cirurgia': guia_date,
                                    'api_hospital_nome': guia.get('hospital'),
                                    'api_cooperado_nome': guia.get('cooperado'),
                                    'matricula': guia.get('matricula'),
                                    'senha': guia.get('senha'),
                                    'plantao_eletiva': guia.get('classificacao')
                                }
                                financas_pending_proc.append((financa_data, len(procedimentos_to_create) - 1))
                                newly_created_count += 1
                                newly_linked_count += 1
                        except Exception as e_proc_create:
                            print(f"Error preparing new Procedimento for Guide CPSA {cpsa_id}: {str(e_proc_create)}")
                            api_errors.append(f"Erro ao criar procedimento para guia {cpsa_id}: {str(e_proc_create)}")
            
            # Bulk create procedures when batch is full
            if len(procedimentos_to_create) >= BATCH_SIZE:
                with transaction.atomic():
                    created_procs = Procedimento.objects.bulk_create(procedimentos_to_create)
                    print(f"--- Bulk created batch of {len(created_procs)} procedimentos ---")
                    # Create financas with proper procedure links
                    for financa_data, proc_idx in financas_pending_proc:
                        financa_data['procedimento'] = created_procs[proc_idx]
                        financas_to_create.append(ProcedimentoFinancas(**financa_data))
                    # Add to lookup dict
                    for proc in created_procs:
                        all_procs_list.append(proc)
                        if proc.nome_paciente and proc.data_horario:
                            lookup_key = (proc.nome_paciente.strip().lower(), proc.data_horario.date())
                            proc_lookup_dict[lookup_key].append(proc)
                procedimentos_to_create = []
                financas_pending_proc = []

            # Process updates in batches to prevent large transactions
            if len(financas_to_update) >= BATCH_SIZE:
                with transaction.atomic():
                    ProcedimentoFinancas.objects.bulk_update(financas_to_update, FINANCAS_UPDATE_FIELDS)
                    updated_records_count += len(financas_to_update)
                    print(f"--- Bulk updated batch of {len(financas_to_update)} financas ---")
                financas_to_update = []
            
            # Process procedure updates in batches
            if len(procedimentos_to_update) >= BATCH_SIZE:
                with transaction.atomic():
                    Procedimento.objects.bulk_update(list(procedimentos_to_update.values()), PROCEDIMENTO_UPDATE_FIELDS)
                    print(f"--- Bulk updated batch of {len(procedimentos_to_update)} procedimentos ---")
                procedimentos_to_update = {}

            # Process creates in batches to prevent large transactions
            if len(financas_to_create) >= BATCH_SIZE:
                with transaction.atomic():
                    ProcedimentoFinancas.objects.bulk_create(financas_to_create)
                    print(f"--- Created batch of {len(financas_to_create)} new records ---")
                financas_to_create = []

        # --- Perform Final DB Operations ---
        # Bulk create any remaining procedures
        if procedimentos_to_create:
            with transaction.atomic():
                created_procs = Procedimento.objects.bulk_create(procedimentos_to_create)
                print(f"--- Bulk created final batch of {len(created_procs)} procedimentos ---")
                for financa_data, proc_idx in financas_pending_proc:
                    financa_data['procedimento'] = created_procs[proc_idx]
                    financas_to_create.append(ProcedimentoFinancas(**financa_data))
                for proc in created_procs:
                    all_procs_list.append(proc)
        
        # Save any remaining procedure updates
        if procedimentos_to_update:
            with transaction.atomic():
                Procedimento.objects.bulk_update(list(procedimentos_to_update.values()), PROCEDIMENTO_UPDATE_FIELDS)
                print(f"--- Bulk updated final batch of {len(procedimentos_to_update)} procedimentos ---")
        
        # Save any remaining financas updates
        if financas_to_update:
            with transaction.atomic():
                ProcedimentoFinancas.objects.bulk_update(financas_to_update, FINANCAS_UPDATE_FIELDS)
                updated_records_count += len(financas_to_update)
                print(f"--- Bulk updated final batch of {len(financas_to_update)} financas ---")

        # Save any remaining creates
        if financas_to_create:
            with transaction.atomic():
                ProcedimentoFinancas.objects.bulk_create(financas_to_create)
                print(f"--- Created final batch of {len(financas_to_create)} new records ---")

        # --- Final Reporting ---
        unprocessed_api_cpsa_ids = set(guias_dict.keys()) - processed_cpsa_ids 
        print(f"--- Conciliation Finished. Updated: {updated_records_count}, Created: {newly_created_count}, Linked: {newly_linked_count}, Unprocessed API CPSA: {len(unprocessed_api_cpsa_ids)} ---")
        if unprocessed_api_cpsa_ids: 
            print(f"Warning: {len(unprocessed_api_cpsa_ids)} CPSA numbers from API were not processed: {list(unprocessed_api_cpsa_ids)}")
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


# ===== CONCILIAÇÃO EM BACKGROUND =====

@login_required
def iniciar_conciliacao_async(request):
    """
    Inicia a conciliação em background e retorna imediatamente.
    O frontend faz polling em status_conciliacao para acompanhar o progresso.
    """
    if not request.user.validado:
        logout(request)
        return JsonResponse({'error': 'Sessão expirada.'}, status=401)
    
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return JsonResponse({'error': 'Acesso negado'}, status=403)
    
    user = request.user
    group = user.group
    
    if not group:
        return JsonResponse({'error': 'Usuário não possui grupo associado'}, status=400)
    if not user.connection_key:
        return JsonResponse({'error': 'Chave de conexão não configurada'}, status=400)
    
    # Auto-cleanup: Mark jobs stuck in 'running' for > 30 minutes as 'failed'
    stale_cutoff = timezone.now() - timedelta(minutes=30)
    stale_jobs = ConciliacaoJob.objects.filter(
        group=group,
        status='running',
        started_at__lt=stale_cutoff
    )
    stale_count = stale_jobs.update(
        status='failed',
        error_message='Job marcado como falho automaticamente (timeout de 30 minutos)',
        completed_at=timezone.now()
    )
    if stale_count > 0:
        print(f"[CONCILIACAO] Auto-cleaned {stale_count} stale jobs for group {group.name}")
    
    # Check if there's already a running job (that isn't stale)
    running_job = ConciliacaoJob.objects.filter(group=group, status='running').first()
    if running_job:
        return JsonResponse({
            'error': 'Já existe uma conciliação em andamento.',
            'job_id': running_job.id
        }, status=409)
    
    # Create new job
    job = ConciliacaoJob.objects.create(
        group=group,
        status='pending',
        current_step='Iniciando conciliação...'
    )
    fast = request.GET.get('fast') == '1'
    force_full = request.GET.get('full') == '1' or not fast
    
    # Start background thread
    def run_conciliation():
        from django.db import connection
        connection.close()  # Close connection before threading
        _run_conciliacao_background(job.id, user.id, force_full=force_full)
    
    thread = threading.Thread(target=run_conciliation, daemon=True)
    thread.start()
    
    return JsonResponse({
        'success': True,
        'message': 'Conciliação iniciada em background.',
        'job_id': job.id
    })


@login_required
def status_conciliacao(request, job_id):
    """
    Retorna o status atual de um job de conciliação.
    O frontend faz polling neste endpoint para atualizar a UI.
    """
    if not request.user.validado:
        return JsonResponse({'error': 'Sessão expirada.'}, status=401)
    
    try:
        job = ConciliacaoJob.objects.get(id=job_id)
    except ConciliacaoJob.DoesNotExist:
        return JsonResponse({'error': 'Job não encontrado'}, status=404)
    
    # Verify user has access to this job
    if job.group != request.user.group:
        return JsonResponse({'error': 'Acesso negado'}, status=403)
    
    return JsonResponse({
        'job_id': job.id,
        'status': job.status,
        'current_step': job.current_step,
        'progress_percent': job.progress_percent,
        'total_guias': job.total_guias,
        'processed_count': job.processed_count,
        'created_count': job.created_count,
        'updated_count': job.updated_count,
        'linked_count': job.linked_count,
        'error_message': job.error_message,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None
    })


def _run_conciliacao_background(job_id, user_id, force_full=False):
    """
    Executa a conciliação em background. Esta função roda em uma thread separada.
    Atualiza o ConciliacaoJob com progresso durante a execução.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        job = ConciliacaoJob.objects.get(id=job_id)
        job.status = 'running'
        job.current_step = 'Buscando dados da API...'
        job.save()
        
        user = User.objects.get(id=user_id)
        group = job.group
        
        # --- Fetch API Data ---
        api_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/guias/ajaxGuias.php"
        start_date = _get_conciliation_start_date(group, force_full=force_full)
        api_payload = {
            "conexao": user.connection_key,
            "periodo_de": start_date.strftime('%Y-%m-%d'),
            "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
            "status": "Listagem Geral",
            "coopahub": "S"
        }
        response = requests.post(api_url, json=api_payload, timeout=120)
        response.raise_for_status()
        api_response_data = response.json()
        
        if api_response_data.get('erro') != '000':
            job.status = 'failed'
            job.error_message = f"API Error: {api_response_data.get('msg', 'Unknown')}"
            job.save()
            return
        
        guias = api_response_data.get('listaguias', [])
        guias_dict = {
            str(g['nrocpsa']): g for g in guias
            if g.get('nrocpsa') and str(g.get('nrocpsa')).strip()
        }
        
        guias_items = _sorted_guias_newest_first(guias_dict)
        job.total_guias = len(guias_items)
        job.current_step = f'Processando {job.total_guias} guias...'
        job.save()
        
        # Run the actual conciliation process
        _execute_conciliation_logic(job, user, group, guias_items, start_date=start_date)
        
        job.status = 'completed'
        job.completed_at = timezone.now()
        job.current_step = 'Concluído!'
        job.save()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            job = ConciliacaoJob.objects.get(id=job_id)
            job.status = 'failed'
            job.error_message = str(e)
            job.save()
        except:
            pass


def _execute_conciliation_logic(job, user, group, guias_items, start_date=None):
    """
    Core conciliation logic - processes guides and updates job progress.
    Similar to conciliar_financas but updates job.processed_count periodically.
    """
    from collections import defaultdict
    
    # Fetch existing data
    financas_qs = ProcedimentoFinancas.objects.filter(
        Q(procedimento__group=group) | Q(group=group)
    ).select_related('procedimento')
    financas_dict_by_cpsa = {f.cpsa: f for f in financas_qs if f.cpsa}

    guias_cpsa_ids = {cpsa_id for cpsa_id, _ in guias_items}
    missing_cpsa_ids = guias_cpsa_ids - set(financas_dict_by_cpsa.keys())
    unlinked_financas_exists = financas_qs.filter(procedimento__isnull=True).exists()
    needs_procedure_matching = bool(missing_cpsa_ids) or unlinked_financas_exists

    cutoff_date = start_date or DATA_INICIO_PUXAR_GUIAS_API
    all_procs_list = []
    proc_lookup_dict = defaultdict(list)
    hospital_cache = {}
    convenio_cache = {}
    surgeon_cache = {}
    anesthesiologist_cache = {}
    proc_detalhes_cache = {}

    if needs_procedure_matching:
        all_procs_qs = Procedimento.objects.filter(
            group=group,
            data_horario__date__gte=cutoff_date
        ).select_related('hospital', 'convenio').prefetch_related('financas_records')
        all_procs_list = list(all_procs_qs)
        
        # Build lookup dictionaries
        for proc in all_procs_list:
            if proc.nome_paciente and proc.data_horario:
                key = (proc.nome_paciente.strip().lower(), proc.data_horario.date())
                proc_lookup_dict[key].append(proc)
        
        # Build entity caches
        hospital_cache = {h.name.lower(): h for h in HospitalClinic.objects.filter(group=group)}
        convenio_cache = {c.name.lower(): c for c in Convenios.objects.all()}
        surgeon_cache = {s.name.lower(): s for s in Surgeon.objects.filter(group=group) if s.name}
        anesthesiologist_cache = {a.name.lower(): a for a in Anesthesiologist.objects.filter(group=group) if a.name}
        proc_detalhes_cache = {pd.codigo_procedimento: pd for pd in ProcedimentoDetalhes.objects.all() if pd.codigo_procedimento}
    
    # Processing
    financas_to_update = []
    financas_to_create = []
    procedimentos_to_update = {}
    procedimentos_to_create = []
    financas_pending_proc = []
    processed_cpsa_ids = set()
    
    BATCH_SIZE = 200
    FINANCAS_UPDATE_FIELDS = [
        'valor_faturado', 'valor_recebido', 'valor_recuperado', 'valor_acatado',
        'status_pagamento', 'api_paciente_nome', 'api_hospital_nome', 'api_cooperado_nome',
        'matricula', 'senha', 'api_data_cirurgia', 'plantao_eletiva', 'procedimento'
    ]
    PROCEDIMENTO_UPDATE_FIELDS = [
        'data_horario', 'data_horario_fim', 'cpf_paciente', 'data_nascimento',
        'acomodacao', 'cirurgiao', 'hospital', 'cooperado', 'procedimento_principal', 'procedimento_type'
    ]
    
    processed_count = 0
    update_interval = max(200, job.total_guias // 10)  # Update every 10% or 200 items
    
    for cpsa_id, guia in guias_items:
        processed_cpsa_ids.add(cpsa_id)
        processed_count += 1
        
        # Update job progress periodically
        if processed_count % update_interval == 0 or processed_count == job.total_guias:
            job.processed_count = processed_count
            job.current_step = f'Processando guia {processed_count} de {job.total_guias}...'
            job.save(update_fields=['processed_count', 'current_step'])
        
        guia_paciente = guia.get('paciente')
        guia_date_str = guia.get('dt_cirurg', guia.get('dt_cpsa'))
        guia_date = parse_api_date(guia_date_str)
        
        if cpsa_id in financas_dict_by_cpsa:
            financa = financas_dict_by_cpsa[cpsa_id]
            # Update existing financa
            updated = False
            guia_valor_faturado = _api_decimal(guia.get('valor_faturado'))
            guia_valor_recebido = _api_decimal(guia.get('valor_recebido'))
            guia_valor_recuperado = _api_decimal(guia.get('valor_receuperado', guia.get('valor_recuperado')))
            guia_valor_acatado = _api_decimal(guia.get('valor_acatado'))

            if guia_valor_faturado is not None and financa.valor_faturado != guia_valor_faturado:
                financa.valor_faturado = guia_valor_faturado; updated = True
            if guia_valor_recebido is not None and financa.valor_recebido != guia_valor_recebido:
                financa.valor_recebido = guia_valor_recebido; updated = True
            if guia_valor_recuperado is not None and financa.valor_recuperado != guia_valor_recuperado:
                financa.valor_recuperado = guia_valor_recuperado; updated = True
            if guia_valor_acatado is not None and financa.valor_acatado != guia_valor_acatado:
                financa.valor_acatado = guia_valor_acatado; updated = True
            api_status = map_api_status(guia.get('STATUS'))
            if financa.status_pagamento != api_status:
                financa.status_pagamento = api_status; updated = True
            if financa.api_paciente_nome != guia.get('paciente'):
                financa.api_paciente_nome = guia.get('paciente'); updated = True
            if financa.api_hospital_nome != guia.get('hospital'):
                financa.api_hospital_nome = guia.get('hospital'); updated = True
            if financa.api_cooperado_nome != guia.get('cooperado'):
                financa.api_cooperado_nome = guia.get('cooperado'); updated = True
            if financa.matricula != guia.get('matricula'):
                financa.matricula = guia.get('matricula'); updated = True
            if financa.senha != guia.get('senha'):
                financa.senha = guia.get('senha'); updated = True
            guia_api_date_parsed = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
            if financa.api_data_cirurgia != guia_api_date_parsed:
                financa.api_data_cirurgia = guia_api_date_parsed; updated = True
            if financa.plantao_eletiva != guia.get('classificacao'):
                financa.plantao_eletiva = guia.get('classificacao'); updated = True
            if updated:
                if financa not in financas_to_update: financas_to_update.append(financa)
            
            if financa.procedimento and needs_procedure_matching:
                was_updated, updated_proc = update_procedimento_with_api_data(financa.procedimento, guia, group, save_immediately=False)
                if was_updated:
                    procedimentos_to_update[updated_proc.id] = updated_proc
            
        else:
            # New financa
            best_match_proc = None
            if guia_paciente and guia_date:
                lookup_key = (guia_paciente.strip().lower(), guia_date)
                candidate_procs = proc_lookup_dict.get(lookup_key, [])
                if not candidate_procs:
                    next_day = guia_date + timedelta(days=1)
                    prev_day = guia_date - timedelta(days=1)
                    candidate_procs = (
                        proc_lookup_dict.get((guia_paciente.strip().lower(), next_day), []) +
                        proc_lookup_dict.get((guia_paciente.strip().lower(), prev_day), [])
                    )
                
                highest_similarity = 0.7
                for proc in candidate_procs:
                    name_similarity = similar(guia_paciente.lower(), proc.nome_paciente.lower())
                    proc_date = proc.data_horario.date() if proc.data_horario else None
                    date_diff = abs((guia_date - proc_date).days) if proc_date else float('inf')
                    if name_similarity > 0.85 and date_diff <= 1 and name_similarity > highest_similarity:
                        highest_similarity = name_similarity
                        best_match_proc = proc
            
            if best_match_proc:
                was_updated, updated_proc = update_procedimento_with_api_data(best_match_proc, guia, group, save_immediately=False)
                if was_updated:
                    procedimentos_to_update[updated_proc.id] = updated_proc
                
                new_financa = ProcedimentoFinancas(
                    procedimento=best_match_proc, group=group, tipo_cobranca='cooperativa', cpsa=cpsa_id,
                    valor_faturado=guia.get('valor_faturado'), valor_recebido=guia.get('valor_recebido'),
                    status_pagamento=map_api_status(guia.get('STATUS')), api_paciente_nome=guia.get('paciente'),
                    api_data_cirurgia=guia_date, api_hospital_nome=guia.get('hospital')
                )
                financas_to_create.append(new_financa)
                job.linked_count += 1
            else:
                if guia_paciente and guia_date:
                    try:
                        proc_obj = prepare_procedimento_from_guia(
                            guia, cpsa_id, group, hospital_cache, convenio_cache,
                            surgeon_cache, anesthesiologist_cache, proc_detalhes_cache
                        )
                        if proc_obj:
                            procedimentos_to_create.append(proc_obj)
                            financa_data = {
                                'group': group, 'tipo_cobranca': 'cooperativa', 'cpsa': cpsa_id,
                                'valor_faturado': guia.get('valor_faturado'), 'valor_recebido': guia.get('valor_recebido'),
                                'status_pagamento': map_api_status(guia.get('STATUS')), 'api_paciente_nome': guia.get('paciente'),
                                'api_data_cirurgia': guia_date, 'api_hospital_nome': guia.get('hospital')
                            }
                            financas_pending_proc.append((financa_data, len(procedimentos_to_create) - 1))
                    except Exception as e:
                        print(f"Error preparing proc: {e}")
        
        # Batch saves
        if len(procedimentos_to_create) >= BATCH_SIZE:
            with transaction.atomic():
                created_procs = Procedimento.objects.bulk_create(procedimentos_to_create)
                for financa_data, proc_idx in financas_pending_proc:
                    financa_data['procedimento'] = created_procs[proc_idx]
                    financas_to_create.append(ProcedimentoFinancas(**financa_data))
            job.created_count += len(procedimentos_to_create)
            procedimentos_to_create = []
            financas_pending_proc = []
        
        if len(financas_to_update) >= BATCH_SIZE:
            with transaction.atomic():
                ProcedimentoFinancas.objects.bulk_update(financas_to_update, FINANCAS_UPDATE_FIELDS)
            job.updated_count += len(financas_to_update)
            financas_to_update = []
        
        if len(procedimentos_to_update) >= BATCH_SIZE:
            with transaction.atomic():
                Procedimento.objects.bulk_update(list(procedimentos_to_update.values()), PROCEDIMENTO_UPDATE_FIELDS)
            procedimentos_to_update = {}
        
        if len(financas_to_create) >= BATCH_SIZE:
            with transaction.atomic():
                ProcedimentoFinancas.objects.bulk_create(financas_to_create)
            financas_to_create = []
    
    # Final batch saves
    if procedimentos_to_create:
        with transaction.atomic():
            created_procs = Procedimento.objects.bulk_create(procedimentos_to_create)
            for financa_data, proc_idx in financas_pending_proc:
                financa_data['procedimento'] = created_procs[proc_idx]
                financas_to_create.append(ProcedimentoFinancas(**financa_data))
        job.created_count += len(procedimentos_to_create)
    
    if procedimentos_to_update:
        with transaction.atomic():
            Procedimento.objects.bulk_update(list(procedimentos_to_update.values()), PROCEDIMENTO_UPDATE_FIELDS)
    
    if financas_to_update:
        with transaction.atomic():
            ProcedimentoFinancas.objects.bulk_update(financas_to_update, FINANCAS_UPDATE_FIELDS)
        job.updated_count += len(financas_to_update)
    
    if financas_to_create:
        with transaction.atomic():
            ProcedimentoFinancas.objects.bulk_create(financas_to_create)
    
    job.processed_count = processed_count
    job.save()


def create_new_procedimento_from_guia(guia, cpsa_id, group):
    """
    Helper function to create a new Procedimento from API guide data.
    This is separated to allow individual transaction handling.
    cpsa_id parameter now contains the nrocpsa value from the API.
    """
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
        proc_data_horario = make_aware_sao_paulo(proc_data_horario)
        
        if guia_hora_final:
            proc_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            proc_data_horario_fim = make_aware_sao_paulo(proc_data_horario_fim)
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
        paciente_nome_para_proc = f"Paciente CPSA {cpsa_id}"

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
            if not created:
                if procedimento_principal_obj.name != api_descricao:
                    procedimento_principal_obj.name = api_descricao
                    procedimento_principal_obj.save() # Decide if overriding name is desired

    proc_type = CIRURGIA_AMBULATORIAL_PROCEDIMENTO
    if procedimento_principal_obj and procedimento_principal_obj.codigo_procedimento == '10101012':
        proc_type = CONSULTA_PROCEDIMENTO

    newly_created_procedimento = Procedimento.objects.create(
        group=group,
        nome_paciente=paciente_nome_para_proc,
        cpf_paciente=guia.get('cpf') or guia.get('nr_cpf'), # Capture CPF
        data_nascimento=parse_api_date(guia.get('data_nascimento')), # Capture birth date (API sends as 'data_nascimento')
        acomodacao=guia.get('tip_acomod'), # Capture accommodation (API sends as 'tip_acomod')
        data_horario=proc_data_horario,
        data_horario_fim=proc_data_horario_fim,
        hospital=hospital_obj,
        convenio=convenio_obj,
        cirurgiao=surgeon_obj,
        procedimento_principal=procedimento_principal_obj, # Assign here
        procedimento_type=proc_type,
        status=STATUS_PENDING
    )
    print(f"Created new Procedimento ID {newly_created_procedimento.id} for patient '{newly_created_procedimento.nome_paciente}' from guide CPSA {cpsa_id}")

    # Handle anesthesiologist
    guia_cooperado = guia.get('cooperado')
    if guia_cooperado:
        anest_final = find_or_create_anesthesiologist(group, guia_cooperado)
        if anest_final:
            # Set as Cooperado (primary)
            newly_created_procedimento.cooperado = anest_final
            newly_created_procedimento.save(update_fields=['cooperado'])

    return newly_created_procedimento


def create_new_procedimento_from_guia_cached(guia, cpsa_id, group, hospital_cache, convenio_cache, 
                                              surgeon_cache, anesthesiologist_cache, proc_detalhes_cache):
    """
    Optimized version of create_new_procedimento_from_guia that uses pre-built caches
    instead of get_or_create for each entity. This dramatically reduces database queries.
    """
    guia_paciente = guia.get('paciente')
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    
    # Parse API time information
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_hora_final = parse_api_time(guia.get('hora_final'))
    
    # Create datetime with time if available
    proc_data_horario = None
    proc_data_horario_fim = None
    
    if guia_date:
        start_time = guia_hora_inicial if guia_hora_inicial else time(8, 0)
        proc_data_horario = datetime.combine(guia_date, start_time)
        proc_data_horario = make_aware_sao_paulo(proc_data_horario)
        
        if guia_hora_final:
            proc_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            proc_data_horario_fim = make_aware_sao_paulo(proc_data_horario_fim)
        else:
            proc_data_horario_fim = proc_data_horario + timedelta(hours=2)
    
    # Use cache for hospital (only 1 query if creating new)
    hospital_obj = None
    api_hospital_name = guia.get('hospital')
    if api_hospital_name and api_hospital_name.strip():
        cache_key = api_hospital_name.strip().lower()
        if cache_key in hospital_cache:
            hospital_obj = hospital_cache[cache_key]
        else:
            hospital_obj, _ = HospitalClinic.objects.get_or_create(
                name__iexact=api_hospital_name.strip(),
                defaults={'name': api_hospital_name.strip(), 'group': group}
            )
            hospital_cache[cache_key] = hospital_obj  # Update cache
    
    # Use cache for convenio
    convenio_obj = None
    api_convenio_name = guia.get('convenio')
    if api_convenio_name and api_convenio_name.strip():
        cache_key = api_convenio_name.strip().lower()
        if cache_key in convenio_cache:
            convenio_obj = convenio_cache[cache_key]
        else:
            convenio_obj, _ = Convenios.objects.get_or_create(
                name__iexact=api_convenio_name.strip(),
                defaults={'name': api_convenio_name.strip()}
            )
            convenio_cache[cache_key] = convenio_obj
    
    # Use cache for surgeon (with similarity fallback)
    surgeon_obj = None
    api_surgeon_name = guia.get('cirurgiao')
    if api_surgeon_name and api_surgeon_name.strip():
        cache_key = api_surgeon_name.strip().lower()
        if cache_key in surgeon_cache:
            surgeon_obj = surgeon_cache[cache_key]
        else:
            # Try similarity match from cache
            best_match = None
            for cached_name, cached_surgeon in surgeon_cache.items():
                if similar(cache_key, cached_name) > 0.85:
                    best_match = cached_surgeon
                    break
            if best_match:
                surgeon_obj = best_match
            else:
                # Create new
                surgeon_obj = Surgeon.objects.create(
                    name=api_surgeon_name.strip(),
                    crm=guia.get('crm_cirurgiao'),
                    group=group
                )
                surgeon_cache[cache_key] = surgeon_obj

    paciente_nome_para_proc = guia_paciente or f"Paciente CPSA {cpsa_id}"

    # Use cache for procedimento principal
    procedimento_principal_obj = None
    proc_type = CIRURGIA_AMBULATORIAL_PROCEDIMENTO
    api_procedimentos = guia.get('procedimentos')
    if api_procedimentos and isinstance(api_procedimentos, list) and len(api_procedimentos) > 0:
        principal_proc_data = api_procedimentos[0]
        api_codigo = principal_proc_data.get('codigo')
        api_descricao = principal_proc_data.get('descricao')
        if api_codigo and api_descricao:
            if api_codigo in proc_detalhes_cache:
                procedimento_principal_obj = proc_detalhes_cache[api_codigo]
            else:
                procedimento_principal_obj, _ = ProcedimentoDetalhes.objects.get_or_create(
                    codigo_procedimento=api_codigo,
                    defaults={'name': api_descricao}
                )
                proc_detalhes_cache[api_codigo] = procedimento_principal_obj
            
            if procedimento_principal_obj.codigo_procedimento == '10101012':
                proc_type = CONSULTA_PROCEDIMENTO

    # Resolve anesthesiologist (cooperado) using cache BEFORE create
    cooperado_obj = None
    guia_cooperado = guia.get('cooperado')
    if guia_cooperado:
        cache_key = guia_cooperado.strip().lower()
        if cache_key in anesthesiologist_cache:
            cooperado_obj = anesthesiologist_cache[cache_key]
        else:
            # Try similarity match
            for cached_name, cached_anest in anesthesiologist_cache.items():
                if similar(cache_key, cached_name) > 0.85:
                    cooperado_obj = cached_anest
                    break
            if not cooperado_obj:
                cooperado_obj = Anesthesiologist.objects.create(name=guia_cooperado.strip(), group=group)
                anesthesiologist_cache[cache_key] = cooperado_obj

    # Create the procedure with all data in a single query
    newly_created_procedimento = Procedimento.objects.create(
        group=group,
        nome_paciente=paciente_nome_para_proc,
        cpf_paciente=guia.get('cpf') or guia.get('nr_cpf'),
        data_nascimento=parse_api_date(guia.get('data_nascimento')),
        acomodacao=guia.get('tip_acomod'),
        data_horario=proc_data_horario,
        data_horario_fim=proc_data_horario_fim,
        hospital=hospital_obj,
        convenio=convenio_obj,
        cirurgiao=surgeon_obj,
        cooperado=cooperado_obj,  # Include cooperado in create
        procedimento_principal=procedimento_principal_obj,
        procedimento_type=proc_type,
        status=STATUS_PENDING
    )

    return newly_created_procedimento


def prepare_procedimento_from_guia(guia, cpsa_id, group, hospital_cache, convenio_cache,
                                    surgeon_cache, anesthesiologist_cache, proc_detalhes_cache):
    """
    Prepare a Procedimento object WITHOUT saving to database.
    Returns the unsaved object for bulk_create.
    Similar to create_new_procedimento_from_guia_cached but doesn't call .create()
    """
    guia_paciente = guia.get('paciente')
    guia_date = parse_api_date(guia.get('dt_cirurg', guia.get('dt_cpsa')))
    
    guia_hora_inicial = parse_api_time(guia.get('hora_inicial'))
    guia_hora_final = parse_api_time(guia.get('hora_final'))
    
    proc_data_horario = None
    proc_data_horario_fim = None
    
    if guia_date:
        start_time = guia_hora_inicial if guia_hora_inicial else time(8, 0)
        proc_data_horario = datetime.combine(guia_date, start_time)
        proc_data_horario = make_aware_sao_paulo(proc_data_horario)
        
        if guia_hora_final:
            proc_data_horario_fim = datetime.combine(guia_date, guia_hora_final)
            proc_data_horario_fim = make_aware_sao_paulo(proc_data_horario_fim)
        else:
            proc_data_horario_fim = proc_data_horario + timedelta(hours=2)
    
    # Use cache for hospital
    hospital_obj = None
    api_hospital_name = guia.get('hospital')
    if api_hospital_name and api_hospital_name.strip():
        cache_key = api_hospital_name.strip().lower()
        if cache_key in hospital_cache:
            hospital_obj = hospital_cache[cache_key]
        else:
            hospital_obj, _ = HospitalClinic.objects.get_or_create(
                name__iexact=api_hospital_name.strip(),
                defaults={'name': api_hospital_name.strip(), 'group': group}
            )
            hospital_cache[cache_key] = hospital_obj
    
    # Use cache for convenio
    convenio_obj = None
    api_convenio_name = guia.get('convenio')
    if api_convenio_name and api_convenio_name.strip():
        cache_key = api_convenio_name.strip().lower()
        if cache_key in convenio_cache:
            convenio_obj = convenio_cache[cache_key]
        else:
            convenio_obj, _ = Convenios.objects.get_or_create(
                name__iexact=api_convenio_name.strip(),
                defaults={'name': api_convenio_name.strip()}
            )
            convenio_cache[cache_key] = convenio_obj
    
    # Use cache for surgeon
    surgeon_obj = None
    api_surgeon_name = guia.get('cirurgiao')
    if api_surgeon_name and api_surgeon_name.strip():
        cache_key = api_surgeon_name.strip().lower()
        if cache_key in surgeon_cache:
            surgeon_obj = surgeon_cache[cache_key]
        else:
            for cached_name, cached_surgeon in surgeon_cache.items():
                if similar(cache_key, cached_name) > 0.85:
                    surgeon_obj = cached_surgeon
                    break
            if not surgeon_obj:
                surgeon_obj = Surgeon.objects.create(
                    name=api_surgeon_name.strip(),
                    crm=guia.get('crm_cirurgiao'),
                    group=group
                )
                surgeon_cache[cache_key] = surgeon_obj

    paciente_nome_para_proc = guia_paciente or f"Paciente CPSA {cpsa_id}"

    # Use cache for procedimento principal
    procedimento_principal_obj = None
    proc_type = CIRURGIA_AMBULATORIAL_PROCEDIMENTO
    api_procedimentos = guia.get('procedimentos')
    if api_procedimentos and isinstance(api_procedimentos, list) and len(api_procedimentos) > 0:
        principal_proc_data = api_procedimentos[0]
        api_codigo = principal_proc_data.get('codigo')
        api_descricao = principal_proc_data.get('descricao')
        if api_codigo and api_descricao:
            if api_codigo in proc_detalhes_cache:
                procedimento_principal_obj = proc_detalhes_cache[api_codigo]
            else:
                procedimento_principal_obj, _ = ProcedimentoDetalhes.objects.get_or_create(
                    codigo_procedimento=api_codigo,
                    defaults={'name': api_descricao}
                )
                proc_detalhes_cache[api_codigo] = procedimento_principal_obj
            
            if procedimento_principal_obj.codigo_procedimento == '10101012':
                proc_type = CONSULTA_PROCEDIMENTO

    # Resolve cooperado using cache
    cooperado_obj = None
    guia_cooperado = guia.get('cooperado')
    if guia_cooperado:
        cache_key = guia_cooperado.strip().lower()
        if cache_key in anesthesiologist_cache:
            cooperado_obj = anesthesiologist_cache[cache_key]
        else:
            for cached_name, cached_anest in anesthesiologist_cache.items():
                if similar(cache_key, cached_name) > 0.85:
                    cooperado_obj = cached_anest
                    break
            if not cooperado_obj:
                cooperado_obj = Anesthesiologist.objects.create(name=guia_cooperado.strip(), group=group)
                anesthesiologist_cache[cache_key] = cooperado_obj

    # Return unsaved Procedimento object (for bulk_create)
    return Procedimento(
        group=group,
        nome_paciente=paciente_nome_para_proc,
        cpf_paciente=guia.get('cpf') or guia.get('nr_cpf'),
        data_nascimento=parse_api_date(guia.get('data_nascimento')),
        acomodacao=guia.get('tip_acomod'),
        data_horario=proc_data_horario,
        data_horario_fim=proc_data_horario_fim,
        hospital=hospital_obj,
        convenio=convenio_obj,
        cirurgiao=surgeon_obj,
        cooperado=cooperado_obj,
        procedimento_principal=procedimento_principal_obj,
        procedimento_type=proc_type,
        status=STATUS_PENDING
    )


@login_required
def get_despesa_recorrente_item(request, id):
    if not request.user.validado:
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)
    
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    user = request.user
    user_group = user.group

    try:
        item = DespesasRecorrentes.objects.get(
            id=id,
            group=user_group
        )
        
        data = {
            'descricao': item.descricao,
            'valor': float(item.valor) if item.valor else 0,
            'periodicidade': item.periodicidade,
            'data_inicio': item.data_inicio.strftime('%Y-%m-%d') if item.data_inicio else None,
            'ativa': item.ativa
        }
        return JsonResponse(data)
    except DespesasRecorrentes.DoesNotExist:
        return JsonResponse({'error': 'Despesa recorrente não encontrada'}, status=404)
    except Exception as e:
        print(f"Error in get_despesa_recorrente_item: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Erro interno ao buscar despesa recorrente'}, status=500)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def create_despesa_recorrente_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

    try:
        data = request.POST
        
        # Parse the date from the form
        data_inicio_str = data.get('data_inicio')
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False, 
                'error': 'Data de início inválida'
            }, status=400)
        
        item = DespesasRecorrentes(
            group=request.user.group,
            descricao=data.get('descricao'),
            valor=clean_money_value(data.get('valor_recorrente')),
            periodicidade=data.get('periodicidade'),
            data_inicio=data_inicio,
            ativa=data.get('ativa') == 'on'
        )
        
        # Add basic validation
        if not item.descricao:
             return JsonResponse({'success': False, 'error': 'Descrição é obrigatória.'}, status=400)
        if item.valor is None:
             return JsonResponse({'success': False, 'error': 'Valor é obrigatório.'}, status=400)
        if not item.periodicidade:
             return JsonResponse({'success': False, 'error': 'Periodicidade é obrigatória.'}, status=400)
        if not item.data_inicio:
             return JsonResponse({'success': False, 'error': 'Data de início é obrigatória.'}, status=400)

        item.save()
        return JsonResponse({'success': True})
        
    except Exception as e:
        print(f"Error creating despesa recorrente: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f"Erro interno ao criar despesa recorrente: {str(e)}"}, status=500)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def update_despesa_recorrente_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)
    
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

    user = request.user
    user_group = user.group

    try:
        data = request.POST
        finance_id = data.get('finance_id')

        item = DespesasRecorrentes.objects.select_for_update().get(
            id=finance_id,
            group=user_group
        )

        # Parse date
        data_inicio_str = data.get('data_inicio')
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Data de início inválida'}, status=400)

        item.descricao = data.get('descricao')
        item.valor = clean_money_value(data.get('valor_recorrente'))
        item.periodicidade = data.get('periodicidade')
        item.data_inicio = data_inicio
        item.ativa = data.get('ativa') == 'on'

        # Basic validation
        if not item.descricao:
             return JsonResponse({'success': False, 'error': 'Descrição é obrigatória.'}, status=400)
        if item.valor is None:
             return JsonResponse({'success': False, 'error': 'Valor é obrigatório.'}, status=400)
        if not item.periodicidade:
             return JsonResponse({'success': False, 'error': 'Periodicidade é obrigatória.'}, status=400)
        if not item.data_inicio:
             return JsonResponse({'success': False, 'error': 'Data de início é obrigatória.'}, status=400)

        item.save()
        return JsonResponse({'success': True})
    except DespesasRecorrentes.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Despesa recorrente não encontrada'}, status=404)
    except Exception as e:
        print(f"Error in update_despesa_recorrente_item: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Erro interno ao atualizar despesa recorrente: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_despesa_recorrente_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'}, status=401)
    active_role = request.user.get_active_role()
    if active_role != GESTOR_USER:
        return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

    user = request.user
    user_group = user.group

    try:
        data = request.POST
        finance_id = data.get('finance_id')

        item = DespesasRecorrentes.objects.get(
            id=finance_id,
            group=user_group
        )

        item.delete()
        return JsonResponse({'success': True})

    except DespesasRecorrentes.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Despesa recorrente não encontrada'}, status=404)
    except Exception as e:
        print(f"Error deleting despesa recorrente: {e}")
        return JsonResponse({'success': False, 'error': f'Erro ao excluir despesa recorrente: {str(e)}'}, status=500)


