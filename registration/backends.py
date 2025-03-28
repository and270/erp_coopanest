import requests
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from constants import ANESTESISTA_USER, GESTOR_USER
from .models import Groups, Membership

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
            
            if 'conexao' in data:
                # Authentication successful, get connection key
                connection_key = data['conexao']
                
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
                user.save()
                
                # Fetch additional user information 
                self._fetch_and_update_user_data(user)
                
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
                "metodo": "empresas"
            }
            
            empresas_response = requests.post(empresas_url, json=empresas_data)
            if empresas_response.status_code == 200:
                user_data_list = empresas_response.json() # Rename to indicate it's a list
                
                # Optional: Print the raw API response if still needed for context
                # print("----- API User Data Response (_fetch_and_update_user_data) -----")
                # print(json.dumps(user_data_list, indent=2))
                # print("-------------------------------------------------------------")
                
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


                    # Update external ID if available (assuming it's in the first item)
                    if 'IdMedico' in first_item:
                        user.external_id = first_item['IdMedico'] # Get from the dictionary

                    # Process user's groups using the entire list received
                    self._process_user_groups(user, user_data_list) # Pass the list directly

                    user.save()
                else:
                    # Handle cases where the response is not a list or is empty
                    print(f"API response for user {user.username} was not a valid list or was empty: {user_data_list}")
                
        except Exception as e:
            # Add the exception type for better debugging
            print(f"Error fetching user data ({type(e).__name__}): {e}") # Updated print
    
    def _process_user_groups(self, user, empresas_list): # Renamed parameter
        """Process and associate user with their groups/empresas from a list."""
        # Check if the received data is actually a list
        if not isinstance(empresas_list, list):
             print("----- _process_user_groups did not receive a list -----")
             print(f"Received data: {empresas_list}")
             print("-------------------------------------------------------")
             return

        # --- Debugging removed/adjusted as the previous step now passes the list ---

        # If user has no empresas, there's nothing to do
        if not empresas_list:
             print("----- Empty empresas list received -----")
             return

        # Process each empresa dictionary in the list
        for empresa_data in empresas_list: # Iterate directly over the list
            external_id = empresa_data.get('id_empresa') # Use the correct key 'id_empresa'
            name = empresa_data.get('razao_social')   # Use the correct key 'razao_social'

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
            
            # Associate user with this group through membership
            membership, _ = Membership.objects.get_or_create(
                user=user,
                group=group,
                defaults={'validado': True}
            )
            
            # TODO: In the future, check empresa_data.get('adm', False) to determine
            # if user is admin of this specific group
            
            # Set the user's active group if not already set
            if not user.group:
                user.group = group
                user.save()