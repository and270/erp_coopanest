from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from agenda.models import Procedimento
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED
from registration.models import Groups, Membership, Anesthesiologist
from .models import ProcedimentoFinancas, Despesas, ConciliacaoTentativa
from django.db.models import Q
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
    
    # Get period parameters
    period = request.GET.get('period', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    
    # Base queryset - Apply filtering based on user type FIRST
    if view_type == 'receitas':
        if user.user_type == ANESTESISTA_USER:
            # Anesthesiologists see only procedures they are responsible for within their group
            queryset = ProcedimentoFinancas.objects.filter(
                procedimento__anestesistas_responsaveis__user=user,
                procedimento__status=STATUS_FINISHED
            ).select_related('procedimento').order_by(
                '-procedimento__data_horario'  # Most recent procedures first
            )
        elif user.user_type == GESTOR_USER:
            # Gestores see all finished procedures in their group
            queryset = ProcedimentoFinancas.objects.filter(
                procedimento__group=user_group,
                procedimento__status=STATUS_FINISHED
            ).select_related('procedimento').order_by(
                '-procedimento__data_horario'  # Most recent procedures first
            )
        else:
            # Handle other user types if necessary, e.g., show nothing or raise permission error
            queryset = ProcedimentoFinancas.objects.none()
    else: # view_type == 'despesas'
        if user.user_type == ANESTESISTA_USER:
            # Anesthesiologists see only expenses linked to procedures they are responsible for
            queryset = Despesas.objects.filter(
                procedimento__anestesistas_responsaveis__user=user,
                procedimento__group=user_group # Ensure procedure is in the correct group
            ).select_related('procedimento').order_by(
                '-data',  # Most recent expenses first
                '-id'     # If same date, newer entries first
            )
        elif user.user_type == GESTOR_USER:
            # Gestores see all expenses linked to their group
            queryset = Despesas.objects.filter(
                group=user_group
            ).select_related('procedimento').order_by(
                '-data',  # Most recent expenses first
                '-id'     # If same date, newer entries first
            )
        else:
            # Handle other user types
            queryset = Despesas.objects.none()
    
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
                'valor_faturado': float(item.valor_faturado) if item.valor_faturado else 0,
                'valor_recebido': float(item.valor_recebido) if item.valor_recebido else 0,
                'valor_recuperado': float(item.valor_recuperado) if item.valor_recuperado else 0,
                'valor_acatado': float(item.valor_acatado) if item.valor_acatado else 0,
                'status_pagamento': item.status_pagamento,
                'data_pagamento': item.data_pagamento.strftime('%Y-%m-%d') if item.data_pagamento else None,
                'cpf': item.procedimento.cpf_paciente,
                'cpsa': item.cpsa,
                'tipo_cobranca': item.tipo_cobranca,
                'tipo_pagamento_direto': item.tipo_pagamento_direto
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
                procedimento__group=user_group
            )
            item.valor_faturado = data.get('valor_faturado')
            item.valor_recebido = data.get('valor_recebido')
            item.valor_recuperado = data.get('valor_recuperado')
            item.valor_acatado = data.get('valor_acatado')
            item.status_pagamento = data.get('status_pagamento')
            item.data_pagamento = data.get('data_pagamento') or None
            item.cpsa = data.get('cpsa')
            item.tipo_cobranca = data.get('tipo_cobranca')
            item.tipo_pagamento_direto = data.get('tipo_pagamento_direto')
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
                'Valor Faturado': float(item.valor_faturado) if item.valor_faturado else 0.0,
                'Valor Recebido': float(item.valor_recebido) if item.valor_recebido else 0.0,
                'Valor Recuperado': float(item.valor_recuperado) if item.valor_recuperado else 0.0,
                'Valor a Recuperar': float(item.valor_acatado) if item.valor_acatado else 0.0,
                'Fonte Pagadora': item.get_tipo_cobranca_display(),
                'CPSA': item.get_cpsa_display(),
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

@login_required
@require_http_methods(["POST"])
def delete_finance_item(request):
    if not request.user.validado:
        return JsonResponse({'success': False, 'error': 'Usuário não autenticado'})
    
    try:
        data = request.POST
        finance_type = data.get('finance_type')
        finance_id = data.get('finance_id')
        user_group = request.user.group

        if finance_type == 'receitas':
            item = ProcedimentoFinancas.objects.get(
                id=finance_id,
                procedimento__group=user_group
            )
        else:
            item = Despesas.objects.get(
                id=finance_id,
                group=user_group
            )
            
        item.delete()
        return JsonResponse({'success': True})
    except (ProcedimentoFinancas.DoesNotExist, Despesas.DoesNotExist):
        return JsonResponse({'error': 'Item não encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

@login_required
def conciliar_financas(request):
    if not request.user.validado:
        return JsonResponse({'error': 'Usuário não autenticado'}, status=401)

    user = request.user
    group = user.group # Conciliar apenas do grupo ativo do usuário

    auto_matched = []
    needs_confirmation = []
    not_found_in_system = [] # Para guias da API sem correspondente no sistema
    
    if group:
        try:
            # Construct API URL and data payload
            api_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/guias/ajaxGuias.php"
            print(f"conexao: {user.connection_key}")
            api_payload = {
                "conexao": user.connection_key,
                "periodo_de": (timezone.now() - timedelta(days=DIAS_PARA_CONCILIACAO)).strftime('%Y-%m-%d'), #TODO: AQUI VAMOS TER UMA DATA FIXA, COMO 01/04/2025.
                "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
                "status": "Listagem Geral" 
            }

            # Make the API call using POST
            response = requests.post(api_url, json=api_payload)
            response.raise_for_status()
            api_data = response.json()

            print(f"api_data: {api_data}")

            # Check for API-specific errors
            if api_data.get('erro') != '000':
                print(f"API Error for group {group.name}: {api_data.get('msg', 'Unknown error')}")
                return JsonResponse({'error': 'Erro na comunicação com a API'}, status=500)

            guias = api_data.get('listaguias', [])
            matched_guias_ids = set() # Guias que já foram associadas a algum procedimento
            
            # Primeiramente, verificar se existe alguma finança já conciliada que precise de atualização
            financas_conciliadas = ProcedimentoFinancas.objects.filter(
                procedimento__group=group,
                tipo_cobranca='cooperativa',  # Apenas para tipo cooperativa
                cpsa__isnull=False  # Já possui CPSA, logo já foi conciliada
            )
            
            if user.user_type == ANESTESISTA_USER:
                financas_conciliadas = financas_conciliadas.filter(
                    procedimento__anestesistas_responsaveis=user.anesthesiologist
                )
                
            for financa in financas_conciliadas:
                # Procurar a guia correspondente para atualizar valores
                guia_match = next((g for g in guias if str(g.get('idcpsa')) == financa.cpsa), None)
                if guia_match:
                    matched_guias_ids.add(guia_match['idcpsa'])
                    # Atualizar valores e status
                    valores_atualizados = False
                    if guia_match.get('valor_faturado') and financa.valor_faturado != float(guia_match['valor_faturado']):
                        financa.valor_faturado = guia_match['valor_faturado']
                        valores_atualizados = True
                    
                    if guia_match.get('valor_recebido') and financa.valor_recebido != float(guia_match['valor_recebido']):
                        financa.valor_recebido = guia_match['valor_recebido']
                        valores_atualizados = True
                        
                    if guia_match.get('valor_receuperado') and financa.valor_recuperado != float(guia_match['valor_receuperado']):
                        financa.valor_recuperado = guia_match['valor_receuperado']
                        valores_atualizados = True
                        
                    if guia_match.get('valor_acatado') and financa.valor_acatado != float(guia_match['valor_acatado']):
                        financa.valor_acatado = guia_match['valor_acatado']
                        valores_atualizados = True
                    
                    # Mapear status da API para o modelo
                    api_status = str(guia_match.get('STATUS', '')).lower()
                    status_mapping = {
                        'em processamento': 'em_processamento',
                        'aguardando pagamento': 'aguardando_pagamento',
                        'recurso de glosa': 'recurso_de_glosa',
                        'processo finalizado': 'processo_finalizado',
                        'cancelada': 'cancelada',
                    }
                    
                    if api_status.lower() in status_mapping and financa.status_pagamento != status_mapping[api_status.lower()]:
                        financa.status_pagamento = status_mapping[api_status.lower()]
                        valores_atualizados = True
                    
                    if valores_atualizados:
                        financa.save()
                        auto_matched.append({
                            'tipo': 'atualizado',
                            'paciente': guia_match.get('paciente', 'Sem nome'),
                            'data': guia_match.get('dt_cirurg', guia_match.get('dt_cpsa')),
                            'valor': guia_match.get('valor_faturado'),
                            'status': guia_match.get('STATUS')
                        })
            
            # Agora, procuramos por financas não conciliadas (sem cpsa)
            base_queryset = ProcedimentoFinancas.objects.filter(
                procedimento__group=group,
                procedimento__status=STATUS_FINISHED,
                tipo_cobranca='cooperativa',  # Apenas para tipo cooperativa
                cpsa__isnull=True  # Ainda não conciliadas
            ).exclude(
                conciliacaotentativa__conciliado__isnull=False
            )

            if user.user_type == ANESTESISTA_USER:
                base_queryset = base_queryset.filter(
                    procedimento__anestesistas_responsaveis=user.anesthesiologist
                )
 
            financas = base_queryset.select_related('procedimento')

            # Filtrar guias que não estão em "Aguardando Envio" (para reconciliação normal)
            active_guias = [g for g in guias if g.get('STATUS') != 'Aguardando Envio']
            
            for guia in active_guias:
                # Pular se a guia já foi associada durante a atualização
                if guia.get('idcpsa') in matched_guias_ids:
                    continue
                    
                # Ensure essential data is present
                if not guia.get('paciente') or not guia.get('idcpsa'):
                    continue

                # Verificar se alguma finança pode ser automaticamente conciliada
                found_match = False
                
                # Convert API date string to date object
                api_date = None
                if guia.get('dt_cirurg'):
                    try:
                        api_date = datetime.strptime(guia['dt_cirurg'], '%Y-%m-%d').date()
                    except ValueError:
                        print(f"Warning: Could not parse dt_cirurg '{guia['dt_cirurg']}' for idcpsa {guia['idcpsa']}")
                        pass

                for financa in financas:
                    # Skip if already attempted to match
                    if ConciliacaoTentativa.objects.filter(
                        procedimento_financas=financa,
                        cpsa_id=guia['idcpsa']
                    ).exists():
                        continue

                    # For anestesista, check if they are the cooperado
                    if (user.user_type == ANESTESISTA_USER and 
                        not similar(user.anesthesiologist.name, guia['cooperado']) > 0.8):
                        continue

                    # Get system procedure date
                    proc_date = financa.procedimento.data_horario.date()

                    # Check for exact match
                    exact_name_match = similar(guia['paciente'], financa.procedimento.nome_paciente) >= 0.95
                    exact_date_match = api_date == proc_date if api_date else False

                    if exact_name_match and exact_date_match:
                        # Auto conciliate
                        ConciliacaoTentativa.objects.create(
                            procedimento_financas=financa,
                            cpsa_id=str(guia['idcpsa']),
                            conciliado=True
                        )

                        # Update ProcedimentoFinancas with all data from the guia
                        financa.cpsa = str(guia['idcpsa'])
                        financa.valor_faturado = guia.get('valor_faturado', 0)
                        financa.valor_recebido = guia.get('valor_recebido', 0) 
                        financa.valor_recuperado = guia.get('valor_receuperado', 0)
                        financa.valor_acatado = guia.get('valor_acatado', 0)
                        
                        # Map API status
                        api_status = str(guia.get('STATUS', '')).lower()
                        status_mapping = {
                            'em processamento': 'em_processamento',
                            'aguardando pagamento': 'aguardando_pagamento',
                            'recurso de glosa': 'recurso_de_glosa',
                            'processo finalizado': 'processo_finalizado',
                            'cancelada': 'cancelada',
                        }

                        if api_status.lower() in status_mapping:
                            financa.status_pagamento = status_mapping[api_status.lower()]
                        else:
                            financa.status_pagamento = 'em_processamento'
                            
                        financa.save()

                        auto_matched.append({
                            'tipo': 'conciliado',
                            'paciente': guia.get('paciente', 'Sem nome'),
                            'data': guia.get('dt_cirurg', guia.get('dt_cpsa')),
                            'valor': guia.get('valor_faturado'),
                            'status': guia.get('STATUS')
                        })
                        
                        found_match = True
                        matched_guias_ids.add(guia['idcpsa'])
                        break

                    else:
                        # Check for similar match
                        nome_similar = similar(guia['paciente'], financa.procedimento.nome_paciente) > 0.8

                        data_similar = False
                        if api_date:
                            data_similar = abs((api_date - proc_date).days) <= 1

                        # Match if names are similar AND (dates are similar OR API date is missing)
                        if nome_similar and (data_similar or not api_date):
                            # Check if this potential match already exists in needs_confirmation
                            existing_confirmation = next((item for item in needs_confirmation 
                                if item['financa_id'] == financa.id and item['cpsa_id'] == str(guia['idcpsa'])), None)
                            
                            if not existing_confirmation:
                                needs_confirmation.append({
                                    'financa_id': financa.id,
                                    'cpsa_id': str(guia['idcpsa']),
                                    'api_data': {
                                        'paciente': guia.get('paciente', 'Sem nome'),
                                        'data': guia.get('dt_cirurg', guia.get('dt_cpsa')),
                                        'valor': guia.get('valor_faturado'),
                                        'status': guia.get('STATUS'),
                                        'hospital': guia.get('hospital', ''),
                                        'cooperado': guia.get('cooperado', '')
                                    },
                                    'sistema_data': {
                                        'paciente': financa.procedimento.nome_paciente,
                                        'data': financa.procedimento.data_horario.strftime('%Y-%m-%d'),
                                        'hospital': financa.procedimento.hospital.name if financa.procedimento.hospital else '',
                                        'anestesista': financa.procedimento.anestesistas_responsaveis.first().name if financa.procedimento.anestesistas_responsaveis.exists() else ''
                                    }
                                })
                                found_match = True
                
                # Se não encontrou match e é um gestor, adiciona para possível visualização
                if not found_match and user.user_type == GESTOR_USER and guia.get('STATUS') != 'Aguardando Envio':
                    not_found_in_system.append({
                        'cpsa_id': str(guia['idcpsa']),
                        'paciente': guia.get('paciente', 'Sem nome'),
                        'data': guia.get('dt_cirurg', guia.get('dt_cpsa')),
                        'valor': guia.get('valor_faturado'),
                        'status': guia.get('STATUS'),
                        'hospital': guia.get('hospital', ''),
                        'cooperado': guia.get('cooperado', '')
                    })
            
            # Buscar procedimentos sem finança que poderiam ser conciliados
            if user.user_type == GESTOR_USER:
                procedures_without_finance = Procedimento.objects.filter(
                    group=group,
                    status=STATUS_FINISHED    #TODO:AQUI, VAMOS VER O QUE O CLIENTE QUER, SE DE FATO OBRIGAR  FINALIZAÇÃO PARA CONCILIAR OU NÃO. POR ENQUANTO, VEJA QUE MESMO A TENTATIVA DE CONCILIAR VIA PROCEDIMENTO (NÃO COM O OBJETO FINANÇAS), ESTÁ FILTRABDO O FINALIZADO, O QUE DE FATO ACABA TORNANDO INÓQUO POIS, PARA ESTAR COM STATUS DE FINALIAZO, É NECESSÁRIO TER FINALIZADO VIA "QUALIDADE, O QUE CRIA O OBJETO FINANÇAS.
                ).exclude(
                    financas__isnull=False
                )
                
                for proc in procedures_without_finance:
                    for guia in active_guias:
                        if guia.get('idcpsa') in matched_guias_ids or not guia.get('paciente'):
                            continue
                            
                        # Convert API date string to date object
                        api_date = None
                        if guia.get('dt_cirurg'):
                            try:
                                api_date = datetime.strptime(guia['dt_cirurg'], '%Y-%m-%d').date()
                            except ValueError:
                                continue
                        
                        # Get system procedure date
                        proc_date = proc.data_horario.date()
                        
                        # Check for match
                        nome_similar = similar(guia['paciente'], proc.nome_paciente) > 0.8
                        data_similar = False
                        if api_date:
                            data_similar = abs((api_date - proc_date).days) <= 1
                            
                        if nome_similar and (data_similar or not api_date):
                            # Criar objeto ProcedimentoFinancas
                            financa = ProcedimentoFinancas.objects.create(
                                procedimento=proc,
                                tipo_cobranca='cooperativa',
                                cpsa=str(guia['idcpsa']),
                                valor_faturado=guia.get('valor_faturado', 0),
                                valor_recebido=guia.get('valor_recebido', 0),
                                valor_recuperado=guia.get('valor_receuperado', 0),
                                valor_acatado=guia.get('valor_acatado', 0)
                            )
                            
                            # Map API status
                            api_status = str(guia.get('STATUS', '')).lower()
                            status_mapping = {
                                'em processamento': 'em_processamento',
                                'aguardando pagamento': 'aguardando_pagamento',
                                'recurso de glosa': 'recurso_de_glosa',
                                'processo finalizado': 'processo_finalizado',
                                'cancelada': 'cancelada',
                            }

                            if api_status.lower() in status_mapping:
                                financa.status_pagamento = status_mapping[api_status.lower()]
                            else:
                                financa.status_pagamento = 'em_processamento'
                            
                            financa.save()
                            
                            # Registrar a tentativa
                            ConciliacaoTentativa.objects.create(
                                procedimento_financas=financa,
                                cpsa_id=str(guia['idcpsa']),
                                conciliado=True
                            )
                            
                            auto_matched.append({
                                'tipo': 'criado_e_conciliado',
                                'paciente': guia.get('paciente', 'Sem nome'),
                                'data': guia.get('dt_cirurg', guia.get('dt_cpsa')),
                                'valor': guia.get('valor_faturado'),
                                'status': guia.get('STATUS')
                            })
                            
                            matched_guias_ids.add(guia['idcpsa'])
                            break

        except requests.exceptions.RequestException as e:
            print(f"Error calling Coopahub API for group {group.name}: {str(e)}")
            return JsonResponse({'error': f'Erro na comunicação com a API: {str(e)}'}, status=500)
        except Exception as e:
            print(f"Error processing data for group {group.name}: {str(e)}")
            return JsonResponse({'error': f'Erro ao processar dados: {str(e)}'}, status=500)

    else:
        return JsonResponse({'error': 'Usuário não possui grupos validados'}, status=403)

    return JsonResponse({
        'auto_matched': auto_matched,
        'needs_confirmation': needs_confirmation,
        'not_found_in_system': not_found_in_system
    })

@login_required
@require_http_methods(["POST"])
def confirmar_conciliacao(request):
    try:
        data = json.loads(request.body)
        financa_id = data.get('financa_id')
        cpsa_id = data.get('cpsa_id')
        conciliado = data.get('conciliado')
        pular = data.get('pular', False)
        
        financa = ProcedimentoFinancas.objects.get(id=financa_id)
        
        # Check if user belongs to the same group as the finança
        if request.user.group != financa.procedimento.group:
            return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)
            
        # Check if anestesista is trying to reconcile another anestesista's procedure
        if (request.user.user_type == ANESTESISTA_USER and 
            not financa.procedimento.anestesistas_responsaveis.filter(id=request.user.anesthesiologist.id).exists()):
            return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)
        
        if pular:
            # Registra apenas que foi pulado (sem confirmar ou recusar)
            ConciliacaoTentativa.objects.create(
                procedimento_financas=financa,
                cpsa_id=cpsa_id,
                conciliado=None  # Null indica que foi pulado
            )
            return JsonResponse({'success': True, 'action': 'skipped'})
        
        # Create conciliation attempt record
        ConciliacaoTentativa.objects.create(
            procedimento_financas=financa,
            cpsa_id=cpsa_id,
            conciliado=conciliado
        )
        
        if conciliado:
            # Update ProcedimentoFinancas with API data
            api_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/guias/ajaxGuias.php"
            api_payload = {
                "conexao": request.user.connection_key,
                "idcpsa": cpsa_id
            }
            
            # Make the API call using POST to get specific guide
            response = requests.post(api_url, json=api_payload)
            response.raise_for_status()
            api_data = response.json()
            
            if api_data.get('erro') == '000' and api_data.get('listaguias'):
                guia = api_data['listaguias'][0]
                
                # Update all values
                financa.cpsa = cpsa_id
                financa.valor_faturado = guia.get('valor_faturado', 0)
                financa.valor_recebido = guia.get('valor_recebido', 0)
                financa.valor_recuperado = guia.get('valor_receuperado', 0)
                financa.valor_acatado = guia.get('valor_acatado', 0)
                
                # Map API status
                api_status = str(guia.get('STATUS', '')).lower()
                status_mapping = {
                    'em processamento': 'em_processamento',
                    'aguardando pagamento': 'aguardando_pagamento',
                    'recurso de glosa': 'recurso_de_glosa',
                    'processo finalizado': 'processo_finalizado',
                    'cancelada': 'cancelada',
                }
                
                if api_status.lower() in status_mapping:
                    financa.status_pagamento = status_mapping[api_status.lower()]
                else:
                    financa.status_pagamento = 'em_processamento'
                
                financa.save()
                
                return JsonResponse({
                    'success': True, 
                    'action': 'conciliado',
                    'data': {
                        'valor_faturado': financa.valor_faturado,
                        'status_pagamento': financa.status_pagamento
                    }
                })
            else:
                return JsonResponse({'success': False, 'error': 'Guia não encontrada na API'})
        
        return JsonResponse({'success': True, 'action': 'rejeitado'})
        
    except ProcedimentoFinancas.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Procedimento financeiro não encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
