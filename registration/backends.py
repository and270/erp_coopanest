import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()

class CoopahubAuthBackend(ModelBackend):
    """
    Authenticate against the Coopahub API.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
            
        # Make API call to Coopahub login endpoint
        login_url = "https://aplicacao.coopanestrio.org.br/portal/acesso/loginportal.php"
        login_data = {
            "login": username,
            "senha": password,
            "origem": "PF"  # Default to PF, could be made configurable
        }
        
        try:
            response = requests.post(login_url, json=login_data)
            data = response.json()
            
            if 'conexao' in data:
                # Authentication successful, get or create user
                connection_key = data['conexao']
                
                # You might want to make additional API calls to get user info
                # like user type using the connection key
                
                try:
                    user = User.objects.get(username=username)
                    # Update user details if needed
                    user.connection_key = connection_key
                    user.save()
                except User.DoesNotExist:
                    # Create a new user - minimal details for now
                    user = User.objects.create_user(
                        username=username,
                        email=f"{username}@example.com",  # Default email, update as needed
                    )
                    user.connection_key = connection_key
                    user.save()
                
                return user
            
            return None
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return None