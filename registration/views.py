from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import CustomUserLoginForm, AnesthesiologistForm, GestorAnesthesiologistConfirmForm, SurgeonForm, HospitalClinicForm, TermsAgreementForm
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
from django.contrib import messages # Keep for potential messages

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
                
                # Check if terms need to be agreed
                if not user.terms_agreed or not user.privacy_policy_agreed:
                    # For all users, send to the appropriate terms page
                    if user.user_type == GESTOR_USER:
                        return redirect('gestor_anesthesiologist_confirm')
                    else:
                        return redirect('terms_agreement')
                
                # If terms already agreed but GESTOR needs anesthesiologist check
                elif (user.user_type == GESTOR_USER and 
                      not Anesthesiologist.objects.filter(user=user).exists() and 
                      not user.gestor_anesthesiologist_check_complete):
                    return redirect('gestor_anesthesiologist_confirm')
                
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

    # Allow only GESTOR and ADMIN
    if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
        # return render(request, 'usuario_fora_funcao.html') # Or redirect to home
        return redirect('home') # Redirect home if not authorized

    # Remove AnesthesiologistForm instantiation
    # anesthesiologist_form = AnesthesiologistForm(user=request.user)
    surgeon_form = SurgeonForm()
    hospital_clinic_form = HospitalClinicForm()

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        # Remove 'anesthesiologist' case
        # if form_type == 'anesthesiologist':
        #     form = AnesthesiologistForm(request.POST, user=request.user)
        if form_type == 'surgeon':
            form = SurgeonForm(request.POST)
        elif form_type == 'hospital_clinic':
            form = HospitalClinicForm(request.POST)
        else:
            # Form type is invalid or missing
            form = None # Explicitly set form to None
            error_message = 'Formulário inválido ou tipo não reconhecido.'

        # Check if a valid form was identified and then if it's valid
        if form and form.is_valid():
            # Pass the request.user to save method to associate the group
            form.save(user=request.user)
            return redirect('members')
        else:
            # If form is None or form is not valid, re-render with errors
            # Determine which form had the error if possible, otherwise show generic error
            if form_type == 'surgeon' and form: # Check if form exists (wasn't invalid type)
                surgeon_form = form # Keep the submitted form with errors
            elif form_type == 'hospital_clinic' and form:
                hospital_clinic_form = form # Keep the submitted form with errors

            return render(request, 'cadastro.html', {
                # 'anesthesiologist_form': anesthesiologist_form, # Remove
                'surgeon_form': surgeon_form,
                'hospital_clinic_form': hospital_clinic_form,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'error_message': 'Por favor, corrija os erros no formulário.' if form else error_message, # Use specific or generic error
                'active_tab': form_type if form_type in ['surgeon', 'hospital_clinic'] else 'surgeons' # Default to surgeons tab on error
            })
    else:
        # GET request
        return render(request, 'cadastro.html', {
            # 'anesthesiologist_form': anesthesiologist_form, # Remove
            'surgeon_form': surgeon_form,
            'hospital_clinic_form': hospital_clinic_form,
            'GESTOR_USER': GESTOR_USER,
            'ADMIN_USER': ADMIN_USER,
            'ANESTESISTA_USER': ANESTESISTA_USER,
            'active_tab': 'surgeons' # Default to surgeons tab on initial load
        })

@login_required
def edit_view(request, model_name, object_id):
    if not request.user.validado:
        return render(request, 'usuario_nao_autenticado.html')

    instance = None
    form_class = None
    template_name = None

    if model_name == 'anesthesiologist':
        instance = get_object_or_404(Anesthesiologist, id=object_id)
        # Permission Check: User must be GESTOR/ADMIN in the *same group* or the specific ANESTESISTA user
        is_correct_user = (request.user.user_type == ANESTESISTA_USER and instance.user == request.user)
        is_group_manager = (request.user.user_type in [GESTOR_USER, ADMIN_USER] and instance.group == request.user.group)

        if not (is_correct_user or is_group_manager):
             return redirect('home') # Or show permission denied

        form_class = AnesthesiologistForm
        template_name = 'edit_anesthesiologist.html'

    elif model_name == 'surgeon':
        instance = get_object_or_404(Surgeon, id=object_id)
        # Permission Check: User must be GESTOR/ADMIN in the *same group*
        if not (request.user.user_type in [GESTOR_USER, ADMIN_USER] and instance.group == request.user.group):
            return redirect('home')
        form_class = SurgeonForm
        template_name = 'edit_surgeon.html'

    elif model_name == 'hospital_clinic':
        instance = get_object_or_404(HospitalClinic, id=object_id)
         # Permission Check: User must be GESTOR/ADMIN in the *same group*
        if not (request.user.user_type in [GESTOR_USER, ADMIN_USER] and instance.group == request.user.group):
            return redirect('home')
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

    # Handle case where user has no active group assigned *before* checking type
    if not user_group:
        # Instead of an error page, maybe show a specific message or redirect to profile
        # For now, rendering a simple message template.
        return render(request, 'generic_message.html', {
            'message_title': 'Grupo não definido',
            'message_body': 'Você não está associado a um grupo ativo no momento. Por favor, verifique seu perfil ou selecione um grupo.',
            'GESTOR_USER': GESTOR_USER, # Pass these for layout consistency if needed
            'ADMIN_USER': ADMIN_USER,
            'ANESTESISTA_USER': ANESTESISTA_USER,
         })

    if request.user.user_type == ANESTESISTA_USER:
        # Anestesista only sees their own record
        my_anesthesiologist_record = Anesthesiologist.objects.filter(user=request.user, group=user_group).first()

        return render(request, 'members.html', {
            'my_anesthesiologist_record': my_anesthesiologist_record,
            'GESTOR_USER': GESTOR_USER,
            'ADMIN_USER': ADMIN_USER,
            'ANESTESISTA_USER': ANESTESISTA_USER,
        })

    elif request.user.user_type in [GESTOR_USER, ADMIN_USER]:
        # Gestor/Admin sees all members in the group
        anesthesiologists = Anesthesiologist.objects.filter(group=user_group)
        surgeons = Surgeon.objects.filter(group=user_group)
        hospitals = HospitalClinic.objects.filter(group=user_group)

        return render(request, 'members.html', {
            'anesthesiologists': anesthesiologists,
            'surgeons': surgeons,
            'hospitals': hospitals,
            'GESTOR_USER': GESTOR_USER,
            'ADMIN_USER': ADMIN_USER,
            'ANESTESISTA_USER': ANESTESISTA_USER,
        })
    else:
        # Should not happen if user types are well defined, but handle defensively
        return HttpResponseForbidden("Tipo de usuário não reconhecido ou sem permissão para ver membros.")

@login_required
def delete_view(request, model_name, object_id):
    # Check validation and base permissions first
    if not request.user.validado:
        return HttpResponseForbidden("Você não tem permissão para acessar esta funcionalidade.")

    if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
         return HttpResponseForbidden("Você não tem permissão para deletar registros.")

    instance = None
    model_class = None

    # Determine model and fetch instance, checking permissions
    if model_name == 'anesthesiologist':
        return HttpResponseForbidden("Anestesiologistas não podem ser deletados.")
    elif model_name == 'surgeon':
        model_class = Surgeon
        instance = get_object_or_404(model_class, id=object_id)
    elif model_name == 'hospital_clinic':
        model_class = HospitalClinic
        instance = get_object_or_404(model_class, id=object_id)
    else:
        messages.error(request, "Tipo de registro inválido para exclusão.")
        return redirect('members')

    # Check group permission
    # Ensure instance was found before checking group
    if instance and instance.group != request.user.group:
         return HttpResponseForbidden("Você só pode deletar registros do seu próprio grupo.")

    # If checks pass, proceed with deletion (assuming GET or POST after browser confirm)
    try:
        instance_name = str(instance)
        instance.delete()
        messages.success(request, f"{model_class._meta.verbose_name.title()} '{instance_name}' deletado com sucesso.")
    except Exception as e:
        messages.error(request, f"Erro ao deletar o registro: {e}")
        # Log the error e.g., logger.error(f"Error deleting {model_name} {object_id}: {e}")

    # Redirect back to members list regardless of GET/POST or success/error (within try/except)
    return redirect('members')

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

    # Allow only GESTOR and ADMIN
    if request.user.user_type not in [GESTOR_USER, ADMIN_USER]:
        # return render(request, 'usuario_fora_funcao.html')
         return redirect('home') # Redirect home if not authorized

    # Remove AnesthesiologistForm
    surgeon_form = SurgeonForm()
    hospital_clinic_form = HospitalClinicForm()

    # Determine default active tab if provided tab is invalid
    valid_tabs = ['surgeons', 'hospitals']
    active_tab = tab if tab in valid_tabs else 'surgeons' # Default to surgeons

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        form = None
        error_message = 'Formulário inválido. Por favor, tente novamente.' # Default error

        # Remove anesthesiologist case
        if form_type == 'surgeon':
            form = SurgeonForm(request.POST)
            active_tab = 'surgeons' # Ensure tab matches submitted form
        elif form_type == 'hospital_clinic':
            form = HospitalClinicForm(request.POST)
            active_tab = 'hospitals' # Ensure tab matches submitted form
        else:
            form = None # Invalid form type

        if form and form.is_valid():
            form.save(user=request.user) # Pass user to set group
            return redirect('members')
        else:
            # Form is invalid or type was wrong
            if form_type == 'surgeon' and form:
                 surgeon_form = form # Keep invalid form data
            elif form_type == 'hospital_clinic' and form:
                 hospital_clinic_form = form # Keep invalid form data

            return render(request, 'cadastro.html', {
                # 'anesthesiologist_form': anesthesiologist_form, # Remove
                'surgeon_form': surgeon_form,
                'hospital_clinic_form': hospital_clinic_form,
                'GESTOR_USER': GESTOR_USER,
                'ADMIN_USER': ADMIN_USER,
                'ANESTESISTA_USER': ANESTESISTA_USER,
                'active_tab': active_tab,
                'error_message': 'Por favor, corrija os erros no formulário.' if form else error_message
            })

    # GET request
    return render(request, 'cadastro.html', {
         # 'anesthesiologist_form': anesthesiologist_form, # Remove
        'surgeon_form': surgeon_form,
        'hospital_clinic_form': hospital_clinic_form,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
        'active_tab': active_tab, # Pass the determined active tab
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


@login_required
def gestor_anesthesiologist_confirm(request):
    # Allow access for any GESTOR user that hasn't agreed to terms yet
    if request.user.user_type != GESTOR_USER:
        return redirect('home')
    
    # Check if user already has an Anesthesiologist record or has completed everything
    if (Anesthesiologist.objects.filter(user=request.user).exists() or 
        request.user.gestor_anesthesiologist_check_complete) and request.user.terms_agreed and request.user.privacy_policy_agreed:
        return redirect('home')
    
    if (Anesthesiologist.objects.filter(user=request.user).exists() or request.user.gestor_anesthesiologist_check_complete) and (not request.user.terms_agreed or not request.user.privacy_policy_agreed):
        return redirect('terms_agreement')
    
    if request.method == 'POST':
        form = GestorAnesthesiologistConfirmForm(request.POST)
        if form.is_valid():
            # Set terms agreement flags
            request.user.terms_agreed = form.cleaned_data.get('terms_agreed')
            request.user.privacy_policy_agreed = form.cleaned_data.get('privacy_policy_agreed')
            
            is_anesthesiologist = form.cleaned_data.get('is_anesthesiologist')
            
            if is_anesthesiologist:
                name = form.cleaned_data.get('name')
                crm = form.cleaned_data.get('crm')
                
                # Create Anesthesiologist record for this gestor
                Anesthesiologist.objects.create(
                    user=request.user,
                    group=request.user.group,
                    name=name,
                    crm=crm,
                    function='Anestesista',
                    role_in_group='administrador'  # Default role for gestors who are also anesthesiologists
                )
            
            # Mark as processed in the user model
            request.user.gestor_anesthesiologist_check_complete = True
            request.user.save()
            
            return redirect('home')
    else:
        form = GestorAnesthesiologistConfirmForm()
    
    return render(request, 'gestor_anesthesiologist_confirm.html', {
        'form': form,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })

@login_required
def terms_agreement_view(request):
    # If user already agreed to both, redirect to home
    if request.user.terms_agreed and request.user.privacy_policy_agreed:
        return redirect('home')
    
    # If user is a GESTOR who needs the combined flow, redirect there
    if request.user.user_type == GESTOR_USER and not (Anesthesiologist.objects.filter(user=request.user).exists() or request.user.gestor_anesthesiologist_check_complete) :
        return redirect('gestor_anesthesiologist_confirm')
    
    if request.method == 'POST':
        form = TermsAgreementForm(request.POST)
        if form.is_valid():
            # Update user agreement status
            request.user.terms_agreed = True
            request.user.privacy_policy_agreed = True
            request.user.save()
            
            # Go to home
            return redirect('home')
    else:
        form = TermsAgreementForm()
    
    return render(request, 'terms_agreement.html', {
        'form': form,
        'GESTOR_USER': GESTOR_USER,
        'ADMIN_USER': ADMIN_USER,
        'ANESTESISTA_USER': ANESTESISTA_USER,
    })