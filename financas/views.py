from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER, STATUS_FINISHED
from registration.models import Groups, Membership
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
        ).select_related('procedimento').order_by(
            '-procedimento__data_horario'  # Most recent procedures first
        )
    else:
        queryset = Despesas.objects.filter(
            group=user_group  # Filter despesas by group
        ).select_related('procedimento').order_by(
            '-data',  # Most recent expenses first
            '-id'     # If same date, newer entries first
        )
    
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
                'valor_cobranca': float(item.valor_cobranca) if item.valor_cobranca else 0,
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
            item.valor_cobranca = data.get('valor_cobranca')
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
                'Valor': float(item.valor_cobranca) if item.valor_cobranca else 0.0,
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
    validated_memberships = Membership.objects.filter(
        user=user,
        validado=True
    )
    groups_to_check = [m.group for m in validated_memberships]

    if not groups_to_check:
        return JsonResponse({'error': 'Usuário não possui grupos validados'}, status=403)

    auto_matched = []
    needs_confirmation = []
    
    for group in groups_to_check:
        try:
            # Construct API URL and data payload
            api_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/guias/ajaxGuias.php"
            api_payload = {
                "conexao": user.connection_key,
                "periodo_de": (timezone.now() - timedelta(days=DIAS_PARA_CONCILIACAO)).strftime('%Y-%m-%d'),
                "periodo_ate": timezone.now().strftime('%Y-%m-%d'),
                "status": "Listagem Geral" 
            }

            # Make the API call using POST
            response = requests.post(api_url, json=api_payload)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            api_data = response.json()

            # Check for API-specific errors
            if api_data.get('erro') != '000':
                print(f"API Error for group {group.name}: {api_data.get('msg', 'Unknown error')}")
                continue # Skip this group if API returns an error

            guias = api_data.get('listaguias', [])
            
            base_queryset = ProcedimentoFinancas.objects.filter(
                procedimento__group=group,
                procedimento__status=STATUS_FINISHED
            ).exclude(
                conciliacaotentativa__conciliado__isnull=False
            )

            if user.user_type == ANESTESISTA_USER:
                base_queryset = base_queryset.filter(
                    procedimento__anestesistas_responsaveis=user.anesthesiologist
                )

            financas = base_queryset.select_related('procedimento')

            for guia in guias:
                # Ensure essential data is present
                if not guia.get('paciente') or not guia.get('idcpsa'):
                    continue

                # Convert API date string to date object (handle potential null or format errors)
                api_date = None
                if guia.get('dt_cirurg'):
                    try:
                        api_date = datetime.strptime(guia['dt_cirurg'], '%Y-%m-%d').date()
                    except ValueError:
                        # Handle cases where the date format might be different or invalid
                        print(f"Warning: Could not parse dt_cirurg '{guia['dt_cirurg']}' for idcpsa {guia['idcpsa']}")
                        pass # Continue matching attempt without date

                for financa in financas:
                    # Skip if already attempted to match
                    #TODO: TAMBÉM TEMOS QUE VER OS CASOS PARA FAZER UPDATE DE STATUS, VALORES, ETC... EM GUIAS QUE JÁ FORAM CONCILIDAS OU JPA REGISTYRADAS, ETC...
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
                    exact_name_match = similar(guia['paciente'], financa.procedimento.nome_paciente) >= 0.95 # Use similarity for robustness
                    exact_date_match = api_date == proc_date if api_date else False

                    if exact_name_match and exact_date_match:
                        # Auto conciliate
                        ConciliacaoTentativa.objects.create(
                            procedimento_financas=financa,
                            cpsa_id=str(guia['idcpsa']), # Ensure idcpsa is stored as string
                            conciliado=True
                        )

                        # Update ProcedimentoFinancas with data from the current 'guia'
                        financa.cpsa = str(guia['idcpsa']) # Store the matched CPSA ID
                        financa.valor_cobranca = guia.get('valor_faturado', 0) # Use .get for safety
                        # Map API status to model choices (convert to lower, handle potential variations)
                        api_status = str(guia.get('STATUS', '')).lower()
                        #TODO VERIFICAR SE OS TYPES DE STATUS SÃO REALMENTE OS QUE APARTECEM NO EXEMPLO DE RESPONSE. SE NÃO, VAMOS AJUSTAR OS TYPES
                        #TODO VERRIFICAR SE ESATMOS COMPARANDO CORRETAMENTE AS KEYS DO STATUS ou os valores de display
                        if api_status in [choice[0] for choice in ProcedimentoFinancas.STATUS_PAGAMENTO_CHOICES]:
                             financa.status_pagamento = api_status
                        else:
                             # Handle unknown statuses if necessary, maybe map to 'pendente'
                             print(f"Warning: Unknown API status '{guia.get('STATUS')}' for idcpsa {guia['idcpsa']}. Setting to 'pendente'.")
                             financa.status_pagamento = 'pendente'
                        #TODO Try to parse payment date if available (needs clarification if API provides this)
                        # financa.data_pagamento = ...
                        financa.save()

                        auto_matched.append({
                            'paciente': guia.get('paciente'),
                            'data': guia.get('dt_cirurg'),
                            'valor': guia.get('valor_faturado'),
                            'status': guia.get('STATUS')
                        })
                        break # Move to the next guia once a match is found for this financa

                    else:
                        # Check for similar match
                        nome_similar = similar(guia['paciente'], financa.procedimento.nome_paciente) > 0.8

                        data_similar = False
                        if guia['dt_cirurg']:
                            data_similar = abs((api_date - proc_date).days) <= 1

                        # Match if names are similar AND (dates are similar OR API date is missing)
                        if nome_similar and (data_similar or not api_date):
                            # Check if this potential match already exists in needs_confirmation
                            # to avoid duplicates if one financa matches multiple similar guias
                            existing_confirmation = next((item for item in needs_confirmation if item['financa_id'] == financa.id and item['cpsa_id'] == str(guia['idcpsa'])), None)
                            if not existing_confirmation:
                                needs_confirmation.append({
                                    'financa_id': financa.id,
                                    'cpsa_id': str(guia['idcpsa']), # Ensure string
                                    'api_data': {
                                        'paciente': guia.get('paciente'),
                                        'data': guia.get('dt_cirurg'),
                                        'valor': guia.get('valor_faturado'), # Pass value for confirmation
                                        'status': guia.get('STATUS'),       # Pass status for confirmation
                                        'hospital': guia.get('hospital'),
                                        'cooperado': guia.get('cooperado')
                                    },
                                    'sistema_data': {
                                        'paciente': financa.procedimento.nome_paciente,
                                        'data': financa.procedimento.data_horario.strftime('%Y-%m-%d'),
                                        'hospital': financa.procedimento.hospital.name if financa.procedimento.hospital else '',
                                        'anestesista': financa.procedimento.anestesistas_responsaveis.first().name if financa.procedimento.anestesistas_responsaveis.exists() else ''
                                    }
                                })
                            # Don't break here, allow checking other guias for potentially better matches for this financa

        except requests.exceptions.RequestException as e:
            print(f"Error calling Coopahub API for group {group.name}: {str(e)}")
            continue # Skip to the next group on connection/request errors
        except Exception as e:
            print(f"Error processing data for group {group.name}: {str(e)}")
            continue # Skip to the next group on other processing errors

    return JsonResponse({
        'auto_matched': auto_matched,
        'needs_confirmation': needs_confirmation
    })

@login_required
@require_http_methods(["POST"])
def confirmar_conciliacao(request):
    try:
        data = json.loads(request.body)
        financa_id = data.get('financa_id')
        cpsa_id = data.get('cpsa_id')
        conciliado = data.get('conciliado')
        
        financa = ProcedimentoFinancas.objects.get(id=financa_id)
        
        # Create conciliation attempt record
        ConciliacaoTentativa.objects.create(
            procedimento_financas=financa,
            cpsa_id=cpsa_id,
            conciliado=conciliado
        )
        
        if conciliado:
            # Update ProcedimentoFinancas with API data
            response = requests.get(f'/api/guias/?cpsa_id={cpsa_id}')
            api_data = response.json()
            
            if api_data.get('erro') == '000' and api_data.get('listaguias'):
                guia = api_data['listaguias'][0]
                financa.valor_cobranca = guia['valor_faturado']
                financa.status_pagamento = guia['STATUS'].lower()
                financa.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
