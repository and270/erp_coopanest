from django.shortcuts import render
from django.db.models import Avg, Count, Case, When, F, Q
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from qualidade.models import ProcedimentoQualidade
from agenda.models import ProcedimentoDetalhes, Procedimento
from django.contrib.auth.decorators import login_required

@login_required
def dashboard_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    user_group = request.user.group
    
    procedimento = request.GET.get('procedimento')
    
    # Base queryset with proper joins and group filter
    queryset = ProcedimentoQualidade.objects.select_related(
        'procedimento',
        'procedimento__procedimento_principal'
    ).filter(
        procedimento__status='finished',
        procedimento__group=user_group
    )
    
    if procedimento:
        queryset = queryset.filter(
            procedimento__procedimento_principal__name=procedimento
        )

    total_count = queryset.count()
    avg_delay = queryset.aggregate(
        avg_delay=Avg(F('data_horario_inicio_efetivo') - F('procedimento__data_horario'))
    )['avg_delay']

    metrics = {
        'eventos_adversos': queryset.filter(eventos_adversos_graves=True).count() / total_count * 100 if total_count > 0 else 0,
        'atraso_medio': (f"{avg_delay.days} dias, {int((avg_delay.seconds // 3600)):02d}:{int((avg_delay.seconds % 3600) // 60):02d}" 
                        if avg_delay and avg_delay.days > 0 
                        else f"{int(avg_delay.seconds // 3600):02d}:{int((avg_delay.seconds % 3600) // 60):02d}" if avg_delay 
                        else "00:00"),
        'duracao_media': str(queryset.aggregate(
            avg_duration=Avg(F('data_horario_fim_efetivo') - F('data_horario_inicio_efetivo'))
        )['avg_duration']).split('.')[0].rsplit(':', 1)[0] if total_count > 0 else "00:00",
        'reacoes_alergicas': queryset.filter(reacao_alergica_grave=True).count() / total_count * 100 if total_count > 0 else 0,
        'encaminhamentos_uti': queryset.filter(encaminhamento_uti=True).count() / total_count * 100 if total_count > 0 else 0,
        'ponv': queryset.filter(ponv=True).count() / total_count * 100 if total_count > 0 else 0,
        'dor_pos_operatoria': queryset.filter(dor_pos_operatoria=True).count() / total_count * 100 if total_count > 0 else 0,
        'adesao_checklist': queryset.filter(adesao_checklist=True).count() / total_count * 100 if total_count > 0 else 0,
        'conformidade_protocolos': queryset.filter(conformidade_diretrizes=True).count() / total_count * 100 if total_count > 0 else 0,
        'tecnicas_assepticas': queryset.filter(uso_tecnicas_assepticas=True).count() / total_count * 100 if total_count > 0 else 0,
        'csat_score': queryset.aggregate(Avg('csat_score'))['csat_score__avg'] or 0,
    }

    # Get procedure types for filter (only from the same group)
    procedimentos = ProcedimentoDetalhes.objects.filter(
        procedimento__group=user_group
    ).distinct()

    print(f"duracao_media: {metrics['duracao_media']}")
    return render(request, 'dashboard.html', {
        'metrics': metrics,
        'procedimentos': procedimentos,
        'selected_procedimento': procedimento,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })