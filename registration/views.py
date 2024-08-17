from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, CustomUserLoginForm, AnesthesiologistForm, SurgeonForm, HospitalClinicForm
from .models import Anesthesiologist, Surgeon, HospitalClinic
from django.contrib.auth import authenticate, login
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER

def home_view(request):
    context = {
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    return render(request, 'home.html', context)

def login_register_view(request):
    if request.method == 'POST':
        if 'register' in request.POST:
            register_form = CustomUserCreationForm(request.POST)
            login_form = CustomUserLoginForm()
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return redirect('home')  # Redirect to a homepage or dashboard
        elif 'login' in request.POST:
            login_form = CustomUserLoginForm(request, data=request.POST)
            register_form = CustomUserCreationForm()
            if login_form.is_valid():
                email = login_form.cleaned_data.get('username')
                password = login_form.cleaned_data.get('password')
                user = authenticate(username=email, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('home')  # Redirect to a homepage or dashboard
    else:
        register_form = CustomUserCreationForm()
        login_form = CustomUserLoginForm()

    return render(request, 'login_register.html', {
        'register_form': register_form,
        'login_form': login_form,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def profile_view(request):
    context = {
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    return render(request, 'profile.html', context)


@login_required
def cadastro_view(request):
    # Check if the user is validated and has the appropriate user type
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    if request.user.user_type not in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
        return render(request, 'usuario_fora_funcao.html')
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'anesthesiologist':
            form = AnesthesiologistForm(request.POST)
        elif form_type == 'surgeon':
            form = SurgeonForm(request.POST)
        elif form_type == 'hospital_clinic':
            form = HospitalClinicForm(request.POST)
        
        if form.is_valid():
            form.save()
            return redirect('members')
    else:
        anesthesiologist_form = AnesthesiologistForm()
        surgeon_form = SurgeonForm()
        hospital_clinic_form = HospitalClinicForm()

    return render(request, 'cadastro.html', {
        'anesthesiologist_form': anesthesiologist_form,
        'surgeon_form': surgeon_form,
        'hospital_clinic_form': hospital_clinic_form,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def edit_view(request, model_name, object_id):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    if model_name == 'anesthesiologist':
        instance = get_object_or_404(Anesthesiologist, id=object_id)
        form_class = AnesthesiologistForm
        template_name = 'edit_anesthesiologist.html'

        # ANESTESISTA_USER can only edit their own record
        if request.user.user_type == ANESTESISTA_USER and instance.user != request.user:
            return redirect('home')
        
    elif model_name == 'surgeon':
        if request.user.user_type not in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
            return redirect('home')
        instance = get_object_or_404(Surgeon, id=object_id)
        form_class = SurgeonForm
        template_name = 'edit_surgeon.html'
    elif model_name == 'hospital_clinic':
        if request.user.user_type not in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
            return redirect('home')
        instance = get_object_or_404(HospitalClinic, id=object_id)
        form_class = HospitalClinicForm
        template_name = 'edit_hospital_clinic.html'
    else:
        return redirect('home')

    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect('members')
    else:
        form = form_class(instance=instance)

    return render(request, template_name, {
        'form': form,
        'instance': instance,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })


@login_required
def members_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    if request.user.user_type in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
        anesthesiologists = Anesthesiologist.objects.all()
        surgeons = Surgeon.objects.all()
        hospitals = HospitalClinic.objects.all()
    elif request.user.user_type == ANESTESISTA_USER:
        try:
            anesthesiologist = Anesthesiologist.objects.get(user=request.user)
            # Redirect to the edit view if the user has a record
            return redirect('edit', model_name='anesthesiologist', object_id=anesthesiologist.id)
        except Anesthesiologist.DoesNotExist:
            anesthesiologists = None
            surgeons = hospitals = None
            return render(request, 'members.html', {
                'anesthesiologists': anesthesiologists,
                'surgeons': surgeons,
                'hospitals': hospitals,
                'SECRETARIA_USER': SECRETARIA_USER,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'no_record_message': True  # Pass a flag to show the message
            })
    else:
        anesthesiologists = surgeons = hospitals = None

    return render(request, 'members.html', {
        'anesthesiologists': anesthesiologists,
        'surgeons': surgeons,
        'hospitals': hospitals,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })


#TODO
@login_required
def profile_view(request):
    return render(request, 'profile.html', {
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })
