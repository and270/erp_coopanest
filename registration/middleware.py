import requests
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

class CoopahubConnectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is authenticated and has a connection key
        if request.user.is_authenticated and hasattr(request.user, 'connection_key') and request.user.connection_key:
            # Check if token needs refreshing
            token_refresh_minutes = settings.COOPAHUB_API.get('TOKEN_REFRESH_MINUTES', 30)
            
            if (not request.user.last_token_check or 
                request.user.last_token_check < (timezone.now() - timedelta(minutes=token_refresh_minutes))):
                self.validate_connection_key(request.user)
            
        response = self.get_response(request)
        return response
    
    def validate_connection_key(self, user):
        """Validate the user's connection key and update user data if needed."""
        try:
            validate_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/acesso/ajaxValidaConexao.php"
            validate_data = {"conexao": user.connection_key}
            response = requests.post(validate_url, json=validate_data)
            
            # Update the last checked timestamp
            user.last_token_check = timezone.now()
            user.save()
            
            # If validation is successful, refresh user data
            if response.status_code == 200:
                from registration.views import fetch_user_details_from_api
                fetch_user_details_from_api(user)
                
        except Exception as e:
            print(f"Error validating connection: {e}")