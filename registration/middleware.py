import requests
from django.utils import timezone
from datetime import timedelta

class CoopahubConnectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is authenticated and has a connection key
        if request.user.is_authenticated and hasattr(request.user, 'connection_key'):
            #TODO: Implement logic to check if the token needs refreshing
            # Here you could implement logic to check if the token needs refreshing
            # For example, you might store a timestamp of when the token was last validated
            # and refresh it if it's older than a certain threshold
            
            # Example (pseudocode):
            # if request.user.last_token_check < (timezone.now() - timedelta(minutes=30)):
            #     self.validate_connection_key(request.user)
            pass
            
        response = self.get_response(request)
        return response
    
    def validate_connection_key(self, user):
        """Validate the user's connection key and refresh if needed."""
        try:
            validate_url = "https://aplicacao.coopanestrio.org.br/portal/acesso/ajaxValidaConexao.php"
            validate_data = {"conexao": user.connection_key}
            response = requests.post(validate_url, json=validate_data)

            #TODO: Implement logic to refresh the token if needed
            
            # Update the last checked timestamp
            # user.last_token_check = timezone.now()
            # user.save()
            
            # If validation fails, you might want to force a re-login
            # or attempt to refresh the token automatically
        except Exception as e:
            print(f"Error validating connection: {e}")