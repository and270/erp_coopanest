from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import CustomUserLoginForm, AnesthesiologistForm, SurgeonForm, HospitalClinicForm
from .models import Anesthesiologist, Surgeon, HospitalClinic
from django.contrib.auth import authenticate, login
from constants import GESTOR_USER, ADMIN_USER, ANESTESISTA_USER
from django.http import HttpResponseForbidden
from django.http import FileResponse
from django.conf import settings
import os
from django.db import IntegrityError
from .backends import CoopahubAuthBackend
import requests
from django.utils import timezone
import json

def home_view(request):
    context = {
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    }
    return render(request, 'home.html', context)

def login_register_view(request):
    if request.method == 'POST':
        if 'login' in request.POST:
            login_form = CustomUserLoginForm(request, data=request.POST)
            
            # Get credentials from form
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            # Try to authenticate using custom backend
            # The backend will create/update user and fetch data via _fetch_and_update_user_data
            user = authenticate(
                request, 
                username=username, 
                password=password,
                backend='registration.backends.CoopahubAuthBackend'
            )
            
            if user is not None:
                login(request, user)
                    
                return redirect('home')
            else:
                # Authentication failed, show error
                login_form.add_error(None, 'Credenciais inválidas. Verifique seu login e senha.')
    else:
        login_form = CustomUserLoginForm()

    return render(request, 'login_register.html', {
        'login_form': login_form,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def profile_view(request):
    from registration.models import Membership  # so we can reference it easily

    # Query all of this user's group memberships for the "switch active group" dropdown
    user_memberships = request.user.memberships.select_related('group').all()

    if request.method == 'POST':

        # Distinguish which form was submitted:
        if 'switch_active_group' in request.POST:
            # The user changed the group_id dropdown
            group_id = request.POST.get('group_id')
            membership = get_object_or_404(Membership, user=request.user, group_id=group_id)
            # Switch the user's active group
            request.user.group = membership.group
            # Update validation status based on the chosen membership
            request.user.validado = membership.validado
            request.user.save()
            return redirect('profile')

    # If GET request or no recognized form submission, just render the page
    context = {
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'user_memberships': user_memberships,
    }
    return render(request, 'profile.html', context)

@login_required
def cadastro_view(request):
    # Check if the user is validated and has the appropriate user type
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
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
        if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
            return redirect('home')
        instance = get_object_or_404(Surgeon, id=object_id)
        form_class = SurgeonForm
        template_name = 'edit_surgeon.html'
    elif model_name == 'hospital_clinic':
        if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
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
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })


@login_required
def members_view(request):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')
    
    user_group = request.user.group

    if request.user.user_type in [GESTOR_USER, ADMIN_USER]:
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
    
    if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
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
        # Validate connection first (optional but good practice)
        validate_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/acesso/ajaxValidaConexao.php"
        validate_data = {"conexao": user.connection_key}
        response = requests.post(validate_url, json=validate_data)

        if response.status_code == 200:
            # Connection validated, now get user's company/group information
            empresas_url = f"{settings.COOPAHUB_API['BASE_URL']}/coopaapi/guia/index.php"
            empresas_data = {
                "conexao": user.connection_key,
                "origem": user.origem,
                "metodo": "empresas"
            }

            empresas_response = requests.post(empresas_url, json=empresas_data)
            if empresas_response.status_code == 200:
                user_data_list = empresas_response.json() # Expecting a list

                # --- Debugging Start (optional, can be removed later) ---
                print("----- API User Data Response (fetch_user_details_from_api in views.py) -----")
                print(json.dumps(user_data_list, indent=2))
                print("--------------------------------------------------------------------------")
                # --- Debugging End ---

                # Check if the response is a non-empty list
                if isinstance(user_data_list, list) and user_data_list:
                    # Process data similar to the backend logic
                    first_item = user_data_list[0]

                    # Get admin status from API
                    is_admin = first_item.get('adm_pj', False)
                    # user.is_admin = is_admin # Decide if you still need this based on previous discussion

                    # --- Debugging Start: User Type Logic (in views.py function) ---
                    print(f"--- Debug (views.py): Assigning User Type for {user.username} ---")
                    print(f"User Origem: {user.origem}")
                    print(f"API adm_pj value (is_admin variable): {is_admin}")

                    # Determine user type based on API admin status or origem
                    if is_admin or user.origem == 'PJ':
                        user.user_type = GESTOR_USER
                        print(f"Condition 'is_admin or user.origem == PJ' is TRUE (is_admin={is_admin}, origem={user.origem})")
                        print(f"Assigning User Type: GESTOR_USER")
                    else:
                        user.user_type = ANESTESISTA_USER
                        print(f"Condition 'is_admin or user.origem == PJ' is FALSE (is_admin={is_admin}, origem={user.origem})")
                        print(f"Assigning User Type: ANESTESISTA_USER")

                    print(f"Final User Type Set: {user.user_type}")
                    print(f"--- End Debug: Assigning User Type ---")
                    # --- Debugging End: User Type Logic ---

                    # Update external ID if available
                    if 'IdMedico' in first_item:
                        user.external_id = first_item['IdMedico']

                    # Process and update groups - Need to call the *backend's* method
                    from registration.backends import CoopahubAuthBackend
                    # Use the *instance* method, not the class directly if possible,
                    # though for this static-like processing it might be okay.
                    # Creating a temporary instance is common if needed here.
                    auth_backend_instance = CoopahubAuthBackend()
                    auth_backend_instance._process_user_groups(user, user_data_list) # Pass the list

                    # Update last token check time
                    user.last_token_check = timezone.now()
                    user.save()
                else:
                     print(f"API response for user {user.username} in fetch_user_details_from_api was not a valid list or was empty: {user_data_list}")

        # Optionally handle non-200 status from validation if needed
        # else:
        #    print(f"Connection key validation failed for user {user.username} with status {response.status_code}")

    except Exception as e:
        # Add the exception type for better debugging
        print(f"Error in fetch_user_details_from_api ({type(e).__name__}): {e}")
