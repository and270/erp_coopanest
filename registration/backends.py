import requests
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from constants import ANESTESISTA_USER, GESTOR_USER
from .models import Groups, Membership, Anesthesiologist, USER_TYPE_CHOICES

User = get_user_model()

class CoopahubAuthBackend(ModelBackend):
    """
    Authenticate against the Coopahub API.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
            
        # Determine origin - try both PF and PJ for flexibility
        origins = ['PF', 'PJ']
        
        for origem in origins:
            # Try to authenticate with the current origin
            user = self._try_authenticate(username, password, origem)
            if user:
                return user
                
        return None
    
    def _try_authenticate(self, username, password, origem):
        # Make API call to Coopahub login endpoint
        login_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/acesso/loginportal.php"
        login_data = {
            "login": username,
            "senha": password,
            "origem": origem
        }
        
        try:
            response = requests.post(login_url, json=login_data)
            data = response.json()

            print("----- API Login Response (_try_authenticate) -----")
            print(json.dumps(data, indent=2))
            print("-------------------------------------------------------------")
            
            if 'conexao' in data:
                # Authentication successful, get connection key
                connection_key = data['conexao']
                
                # Extract user name from login response
                user_full_name = data.get('nome', '')
                
                # Check if user exists in our database
                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    # User doesn't exist in our database, create a new one
                    # with minimal information initially
                    user = User(
                        username=username,
                        email=f"{username}@temp.com",  # Temporary email, will be updated later
                        is_active=True,
                        origem=origem
                    )
                    # Save the user to generate an ID
                    user.save()
                
                # Update connection information
                user.connection_key = connection_key
                user.origem = origem
                user.last_token_check = timezone.now()
                user.validado = True  # User is validated through the API
                # Store the user's full name from login response
                user.full_name = user_full_name
                user.save()

                # Process the 'empresa' list directly from the login response
                # This replaces the need for _fetch_and_update_user_data during login
                if 'empresa' in data and isinstance(data['empresa'], list):
                    self._process_user_groups(user, data['empresa'])
                else:
                    # Handle single company response (PJ users)
                    self._process_single_company_response(user, data)
                
                return user
            
        except Exception as e:
            print(f"Authentication error for origin {origem}: {e}")
            return None
    
    def _fetch_and_update_user_data(self, user):
        """Fetch user data from the API and update the user model."""
        if not user.connection_key or not user.origem:
            return
        
        try:
            # Get user's company/group information
            empresas_url = f"{settings.COOPAHUB_API['BASE_URL']}/coopaapi/guia/index.php"
            empresas_data = {
                "conexao": user.connection_key,
                "origem": user.origem,
                "metodo": "empresas",
                "coopahub": "S"  # Added parameter
            }
            
            empresas_response = requests.post(empresas_url, json=empresas_data)
            if empresas_response.status_code == 200:
                user_data_list = empresas_response.json() # Rename to indicate it's a list
                
                # Optional: Print the raw API response if still needed for context
                print("----- API User Data Response (_fetch_and_update_user_data) -----")
                print(json.dumps(user_data_list, indent=2))
                print("-------------------------------------------------------------")
                
                # Check if the response is a non-empty list
                if isinstance(user_data_list, list) and user_data_list:
                    # Assuming adm_pj and IdMedico might be in the first item
                    # If they are not always present or could be elsewhere, this needs adjustment
                    first_item = user_data_list[0]

                    # --- Debugging Start: User Type Logic ---
                    print(f"--- Debug: Assigning User Type for {user.username} ---")
                    print(f"User Origem: {user.origem}")

                    # Get admin status from API
                    is_admin = first_item.get('adm_pj', False) # Get from the dictionary inside the list
                    print(f"API adm_pj value (is_admin variable): {is_admin}")

                    # Determine user type
                    assigned_user_type = GESTOR_USER if is_admin or user.origem == 'PJ' else ANESTESISTA_USER
                    # user.user_type = assigned_user_type # This is now handled per-membership

                    print(f"Condition 'is_admin or user.origem == PJ' is {is_admin or user.origem == 'PJ'} (is_admin={is_admin}, origem={user.origem})")
                    # print(f"Assigning User Type: {assigned_user_type}") # No longer assigned globally
                    print(f"User Type is now determined by group membership role.")
                    print(f"--- End Debug: Assigning User Type ---")
                    # --- Debugging End: User Type Logic ---


                    # Update external ID if available (assuming it's in the first item)
                    if 'IdMedico' in first_item:
                        user.external_id = first_item['IdMedico'] # Get from the dictionary

                    # Process user's groups using the entire list received
                    # Note: This old logic does not have role information.
                    # The middleware will call this. For now, it will just sync groups.
                    self._process_user_groups(user, user_data_list) # Pass the list directly

                    # --- Automatic Anesthesiologist Creation ---
                    # The role is now per-group, so we check the active group's role
                    active_role = user.get_active_role()
                    if active_role == ANESTESISTA_USER and user.group:
                        # Check if an Anesthesiologist record already exists for this user
                        if not Anesthesiologist.objects.filter(user=user).exists():
                            print(f"--- Creating Anesthesiologist record for user {user.username} ---")
                            
                            # Try to get the name from different sources, prioritizing the login response name
                            api_name = getattr(user, 'full_name', '') or first_item.get('nome_completo', '') or first_item.get('nome', '')
                            print(f"API name: {api_name}")
                            
                            # Use API name or fallback to username
                            anesthesiologist_name = api_name if api_name else user.username
                            
                            # Check if an Anesthesiologist with the same name already exists in this group
                            existing_anesthesiologist = None
                            if anesthesiologist_name and user.group:
                                existing_anesthesiologist = Anesthesiologist.objects.filter(
                                    name=anesthesiologist_name, 
                                    group=user.group,
                                    user__isnull=True  # Only consider unlinked records
                                ).first()
                            
                            if existing_anesthesiologist:
                                # Link existing anesthesiologist to this user
                                print(f"--- Found existing Anesthesiologist with name '{anesthesiologist_name}' - linking to user {user.username} ---")
                                existing_anesthesiologist.user = user
                                existing_anesthesiologist.save()
                            else:
                                # Create new anesthesiologist record
                                print(f"--- No existing Anesthesiologist found with name '{anesthesiologist_name}' - creating new record ---")
                                Anesthesiologist.objects.create(
                                    user=user,
                                    group=user.group,
                                    name=anesthesiologist_name
                                )
                            print(f"--- Anesthesiologist record processed for {user.username} ---")
                        else:
                            print(f"--- Anesthesiologist record already exists for user {user.username} ---")
                    # --- End Automatic Creation ---

                    user.save()
                else:
                    # Handle cases where the response is not a list or is empty
                    print(f"API response for user {user.username} was not a valid list or was empty: {user_data_list}")
                
        except Exception as e:
            # Add the exception type for better debugging
            print(f"Error fetching user data ({type(e).__name__}): {e}") # Updated print
    
    def _process_single_company_response(self, user, data):
        """
        Process single company response for PJ users.
        """
        external_id = data.get('id_empresa')
        name = data.get('razao_social')
        
        if not external_id or not name:
            print(f"Invalid single company data for user {user.username}: {data}")
            return
        
        # PJ users are typically managers/gestores
        role = GESTOR_USER
        
        # Get or create group
        group, created = Groups.objects.get_or_create(
            external_id=external_id,
            defaults={'name': name}
        )
        
        # If the group exists but has a different name, update it
        if not created and group.name != name:
            group.name = name
            group.save()
        
        # Get or create membership with GESTOR role
        membership, membership_created = Membership.objects.get_or_create(
            user=user,
            group=group,
            defaults={'validado': True, 'role': role}
        )
        
        # Update role if membership already existed
        if not membership_created and membership.role != role:
            membership.role = role
            membership.save()
        
        # Set the user's active group
        user.group = group
        user.save()
        
        print(f"Processed single company for user {user.username}: {name} (Role: {role})")

    def _process_user_groups(self, user, empresas_list): # Renamed parameter
        """
        Process and associate user with their groups/empresas from a list.
        This function handles two different formats from the API:
        1. The rich format from the login endpoint (`loginportal.php`).
        2. The simple format from the user details endpoint (`guia/index.php`).
        """
        if not isinstance(empresas_list, list):
             print("----- _process_user_groups did not receive a list -----")
             print(f"Received data: {empresas_list}")
             print("-------------------------------------------------------")
             return

        if not empresas_list:
             print("----- Empty empresas list received -----")
             return

        # Process each empresa dictionary in the list
        for empresa_data in empresas_list: # Iterate directly over the list
            # Detect format and extract data
            is_login_format = 'value' in empresa_data and 'label' in empresa_data
            
            if is_login_format:
                external_id = empresa_data.get('value')
                name = empresa_data.get('label')
                role = GESTOR_USER if empresa_data.get('administrador') == 'S' else ANESTESISTA_USER
            else: # Assuming old format
                external_id = empresa_data.get('id_empresa')
                name = empresa_data.get('razao_social')
                # The old format doesn't provide a role, so we can't update it here.
                # We'll just ensure the membership exists.
                role = None 

            if not external_id or not name:
                print(f"Skipping invalid empresa data: {empresa_data}") # Added log
                continue

            # Get or create group
            group, created = Groups.objects.get_or_create(
                external_id=external_id,
                defaults={'name': name}
            )
            
            # If the group exists but has a different name, update it
            if not created and group.name != name:
                group.name = name
                group.save()
            
            # Get or create membership
            membership, membership_created = Membership.objects.get_or_create(
                user=user,
                group=group,
                defaults={'validado': True}
            )

            # Update role only if provided by the API (i.e., login format)
            if role and membership.role != role:
                membership.role = role
                membership.save()
            
            # Set the user's active group if not already set
            if not user.group:
                user.group = group
                user.save()