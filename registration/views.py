from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import AddGroupMembershipForm, CustomUserCreationForm, CustomUserLoginForm, AnesthesiologistForm, SurgeonForm, HospitalClinicForm
from .models import Anesthesiologist, Surgeon, HospitalClinic
from django.contrib.auth import authenticate, login
from constants import SECRETARIA_USER, GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from django.http import HttpResponseForbidden
from django.http import FileResponse
from django.conf import settings
import os
from django.db import IntegrityError
from .backends import CoopahubAuthBackend
import requests
from django.utils import timezone

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
            try:
                if register_form.is_valid():
                    user = register_form.save()
                    login(request, user)
                    return redirect('home')
            except IntegrityError:
                register_form.add_error('email', 'Este email já está cadastrado.')
        elif 'login' in request.POST:
            login_form = CustomUserLoginForm(request, data=request.POST)
            register_form = CustomUserCreationForm()
            
            # Get credentials from form
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            # Authenticate using custom backend
            user = authenticate(
                request, 
                username=username, 
                password=password,
                backend='registration.backends.CoopahubAuthBackend'
            )
            
            if user is not None:
                login(request, user)
                
                # After login, validate connection and fetch user data
                if hasattr(user, 'connection_key') and user.connection_key:
                    # You could add logic here to validate the connection key
                    # and fetch user details from the API
                    # For example:
                    # fetch_user_details_from_api(user)
                    pass
                    
                return redirect('home')
            else:
                # Authentication failed, show error
                login_form.add_error(None, 'Credenciais inválidas.')
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
    from registration.models import Membership  # so we can reference it easily

    # Query all of this user's group memberships for the "switch active group" dropdown
    user_memberships = request.user.memberships.select_related('group').all()

    # We'll instantiate the "AddGroupMembershipForm" with the logged-in user
    add_group_form = AddGroupMembershipForm(user=request.user)

    if request.method == 'POST':

        # Distinguish which form was submitted:
        if 'switch_active_group' in request.POST:
            # The user changed the group_id dropdown
            group_id = request.POST.get('group_id')
            membership = get_object_or_404(Membership, user=request.user, group_id=group_id)
            # Switch the user's active group
            request.user.group = membership.group
            request.user.validado = membership.validado
            request.user.save()
            return redirect('profile')

        elif 'add_group' in request.POST:
            add_group_form = AddGroupMembershipForm(request.POST, user=request.user)
            if add_group_form.is_valid():
                group_obj, is_new_group = add_group_form.create_or_get_group()

                # If the user is Gestor and actually created a brand-new group, validado=True
                gestor_created_new = (
                    request.user.user_type == GESTOR_USER
                    and is_new_group
                )

                membership, created = Membership.objects.get_or_create(
                    user=request.user,
                    group=group_obj,
                    defaults={'validado': gestor_created_new}
                )
            return redirect('profile')

    # If GET request or no recognized form submission, just render the forms
    context = {
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'user_memberships': user_memberships,
        'add_group_form': add_group_form,
    }
    return render(request, 'profile.html', context)

@login_required
def cadastro_view(request):
    # Check if the user is validated and has the appropriate user type
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    if request.user.user_type not in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
        return render(request, 'usuario_fora_funcao.html')
    
    anesthesiologist_form = AnesthesiologistForm(user=request.user)
    surgeon_form = SurgeonForm()
    hospital_clinic_form = HospitalClinicForm()
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'anesthesiologist':
            form = AnesthesiologistForm(request.POST, user=request.user)
        elif form_type == 'surgeon':
            form = SurgeonForm(request.POST)
        elif form_type == 'hospital_clinic':
            form = HospitalClinicForm(request.POST)
        else:
            return render(request, 'cadastro.html', {
                'anesthesiologist_form': anesthesiologist_form,
                'surgeon_form': surgeon_form,
                'hospital_clinic_form': hospital_clinic_form,
                'SECRETARIA_USER': SECRETARIA_USER,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'error_message': 'Formulário inválido. Por favor, tente novamente.'
            })
        
        if form and form.is_valid():
            form.save(user=request.user)
            return redirect('members')
        else:
            # Form is invalid, re-render the page with error messages
            return render(request, 'cadastro.html', {
                'anesthesiologist_form': AnesthesiologistForm(user=request.user) if form_type != 'anesthesiologist' else form,
                'surgeon_form': SurgeonForm() if form_type != 'surgeon' else form,
                'hospital_clinic_form': HospitalClinicForm() if form_type != 'hospital_clinic' else form,
                'SECRETARIA_USER': SECRETARIA_USER,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'error_message': 'Por favor, corrija os erros no formulário.'
            })
    else:
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
    
    user_group = request.user.group

    if request.user.user_type in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
        anesthesiologists = Anesthesiologist.objects.filter(group=user_group)
        surgeons = Surgeon.objects.filter(group=user_group)
        hospitals = HospitalClinic.objects.filter(group=user_group)
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

@login_required
def delete_view(request, model_name, object_id):
    if not request.user.validado:
        return HttpResponseForbidden("Você não tem permissão para deletar este registro.")

    if model_name == 'anesthesiologist':
        instance = get_object_or_404(Anesthesiologist, id=object_id)
    elif model_name == 'surgeon':
        instance = get_object_or_404(Surgeon, id=object_id)
    elif model_name == 'hospital_clinic':
        instance = get_object_or_404(HospitalClinic, id=object_id)
    else:
        return redirect('home')

    if request.method == 'POST':
        instance.delete()
        return redirect('members')

    return render(request, 'confirm_delete.html', {'instance': instance})

def terms_of_service(request):
    file_path = os.path.join(settings.BASE_DIR, 'registration/terms_and_privacy/terms_of_service.pdf')
    return FileResponse(open(file_path, 'rb'), content_type='application/pdf')

def privacy_policy(request):
    file_path = os.path.join(settings.BASE_DIR, 'registration/terms_and_privacy/privacy_policy.pdf')
    return FileResponse(open(file_path, 'rb'), content_type='application/pdf')

@login_required
def cadastro_redirect(request, tab):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    if request.user.user_type not in [SECRETARIA_USER, GESTOR_USER, ADMIN_USER]:
        return render(request, 'usuario_fora_funcao.html')
    
    anesthesiologist_form = AnesthesiologistForm(user=request.user)
    surgeon_form = SurgeonForm()
    hospital_clinic_form = HospitalClinicForm()
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'anesthesiologist':
            form = AnesthesiologistForm(request.POST, user=request.user)
        elif form_type == 'surgeon':
            form = SurgeonForm(request.POST)
        elif form_type == 'hospital_clinic':
            form = HospitalClinicForm(request.POST)
        else:
            return render(request, 'cadastro.html', {
                'anesthesiologist_form': anesthesiologist_form,
                'surgeon_form': surgeon_form,
                'hospital_clinic_form': hospital_clinic_form,
                'SECRETARIA_USER': SECRETARIA_USER,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'active_tab': tab,
                'error_message': 'Formulário inválido. Por favor, tente novamente.'
            })
        
        if form and form.is_valid():
            form.save(user=request.user)
            return redirect('members')
        else:
            # Form is invalid, re-render the page with error messages
            return render(request, 'cadastro.html', {
                'anesthesiologist_form': AnesthesiologistForm(user=request.user) if form_type != 'anesthesiologist' else form,
                'surgeon_form': SurgeonForm() if form_type != 'surgeon' else form,
                'hospital_clinic_form': HospitalClinicForm() if form_type != 'hospital_clinic' else form,
                'SECRETARIA_USER': SECRETARIA_USER,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'active_tab': tab,
                'error_message': 'Por favor, corrija os erros no formulário.'
            })
    
    return render(request, 'cadastro.html', {
        'anesthesiologist_form': anesthesiologist_form,
        'surgeon_form': surgeon_form,
        'hospital_clinic_form': hospital_clinic_form,
        'SECRETARIA_USER': SECRETARIA_USER,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'active_tab': tab,
    })

# Add a utility function to fetch and update user data from the API
def fetch_user_details_from_api(user):
    """
    Fetch additional user details from the Coopahub API using the connection key.
    Update the user model with these details.
    """
    if not user.connection_key or not user.origem:
        return
    
    try:
        # Validate connection
        validate_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/acesso/ajaxValidaConexao.php"
        validate_data = {"conexao": user.connection_key}
        response = requests.post(validate_url, json=validate_data)
        
        if response.status_code == 200:
            # Get user's company/group information
            empresas_url = f"{settings.COOPAHUB_API['BASE_URL']}/coopaapi/guia/index.php"
            empresas_data = {
                "conexao": user.connection_key,
                "origem": user.origem,
                "metodo": "empresas"
            }
            
            empresas_response = requests.post(empresas_url, json=empresas_data)
            if empresas_response.status_code == 200:
                user_data = empresas_response.json()
                
                # Update admin status
                is_admin = user_data.get('adm_pj', False)
                user.is_admin = is_admin
                
                # Update user type based on origem and admin status
                if user.origem == 'PF':
                    user.user_type = ANESTESISTA_USER
                else:  # PJ
                    user.user_type = GESTOR_USER if is_admin else SECRETARIA_USER
                
                # Update external ID if available
                if 'IdMedico' in user_data:
                    user.external_id = user_data['IdMedico']
                
                # Process and update groups
                from registration.backends import CoopahubAuthBackend
                CoopahubAuthBackend()._process_user_groups(user, user_data)
                
                # Update last token check time
                user.last_token_check = timezone.now()
                user.save()
                
    except Exception as e:
        print(f"Error fetching user details: {e}")
