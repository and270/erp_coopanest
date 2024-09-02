from django.shortcuts import render, get_object_or_404, redirect
from .models import Procedimento, EscalaAnestesiologista
from .forms import ProcedimentoForm, EscalaForm
from django.contrib.auth.decorators import login_required

@login_required
def agenda_procedimentos_view(request):
    if not request.user.validado:
        return render(request, 'registration/usuario_nao_autenticado.html')
    procedimentos = Procedimento.objects.all()
    return render(request, 'agenda_procedimentos.html', {'procedimentos': procedimentos})

@login_required
def add_procedimento_view(request):
    if not request.user.validado:
        return render(request, 'registration/usuario_nao_autenticado.html')
    if request.method == 'POST':
        form = ProcedimentoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('agenda_procedimentos')
    else:
        form = ProcedimentoForm()
    return render(request, 'add_procedimento.html', {'form': form})

@login_required
def escala_trabalho_view(request):
    if not request.user.validado:
        return render(request, 'registration/usuario_nao_autenticado.html')
    escalas = EscalaAnestesiologista.objects.all()
    return render(request, 'escala_trabalho.html', {'escalas': escalas})

@login_required
def add_escala_view(request):
    if not request.user.validado:
        return render(request, 'registration/usuario_nao_autenticado.html')
    if request.method == 'POST':
        form = EscalaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('escala_trabalho')
    else:
        form = EscalaForm()
    return render(request, 'add_escala.html', {'form': form})
