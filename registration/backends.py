import requests
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from constants import ANESTESISTA_USER, GESTOR_USER, SECRETARIA_USER
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
                
                # Process user's groups from empresa data
                self._process_user_groups(user, user_data)
                
                user.save()
                
        except Exception as e:
            print(f"Error fetching user data: {e}")
    
    def _process_user_groups(self, user, user_data):
        """Process and associate user with their groups/empresas."""
        if not user_data or 'empresa' not in user_data:
            return
        
        # Get the list of empresas/groups
        empresas = user_data.get('empresa', [])
        
        # If user has no empresas, there's nothing to do
        if not empresas:
            return
        
        # Process each empresa
        for empresa in empresas:
            external_id = empresa.get('value')
            name = empresa.get('label')
            
            if not external_id or not name:
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
            
            # TODO: In the future, check empresa.get('adm', False) to determine
            # if user is admin of this specific group
            
            # Set the user's active group if not already set
            if not user.group:
                user.group = group
                user.save()