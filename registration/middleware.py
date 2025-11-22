import requests
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse, HttpResponseRedirect

class CoopahubConnectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        # Check if user is authenticated and has a connection key
        if user.is_authenticated:
            # Make active_role available globally for templates
            request.active_role = user.get_active_role()

            if hasattr(user, 'connection_key') and user.connection_key:
                # Check if token needs refreshing
                token_refresh_minutes = settings.COOPAHUB_API.get('TOKEN_REFRESH_MINUTES', 30)
                
                if (not user.last_token_check or 
                    user.last_token_check < (timezone.now() - timedelta(minutes=token_refresh_minutes))):
                    early_response = self.validate_connection_key(request)
                    if early_response is not None:
                        return early_response
            
        response = self.get_response(request)
        return response
    
    def validate_connection_key(self, request):
        """Validate the user's connection key and update user data if needed."""
        user = request.user
        try:
            validate_url = f"{settings.COOPAHUB_API['BASE_URL']}/portal/acesso/ajaxValidaConexao.php"
            validate_data = {"conexao": user.connection_key}
            response = requests.post(validate_url, json=validate_data)
            
            # Update the last checked timestamp
            user.last_token_check = timezone.now()
            user.save()
            
            # Try to parse the API response to detect invalid/expired connections
            resp_text = ''
            resp_json = None
            try:
                resp_json = response.json()
            except Exception:
                resp_text = (response.text or '').lower()

            def is_connection_expired():
                # Accept a wide range of messages/shapes
                # Common payloads:
                # - {'erro': '001', 'msg': 'Conexão Encerrada favor logar novamente'}
                # - {'success': False, 'message': 'Sessão expirada'} or similar
                # - plain text containing keywords
                if isinstance(resp_json, dict):
                    # Numeric or string code check
                    erro_code = str(resp_json.get('erro', '')).strip()
                    msg = str(resp_json.get('msg', '')).lower()
                    message = str(resp_json.get('message', '')).lower()
                    detail = str(resp_json.get('detail', '')).lower()
                    if erro_code and erro_code != '000':
                        if any(k in msg for k in ['conexão encerrada', 'conexao encerrada', 'logar novamente', 'sessão expirada', 'sessao expirada', 'expirad']):
                            return True
                        if any(k in message for k in ['conexão encerrada', 'conexao encerrada', 'logar novamente', 'sessão expirada', 'sessao expirada', 'expirad']):
                            return True
                        if any(k in detail for k in ['conexão encerrada', 'conexao encerrada', 'logar novamente', 'sessão expirada', 'sessao expirada', 'expirad']):
                            return True
                    # Some APIs may send explicit booleans/flags
                    if str(resp_json.get('valid', '')).lower() in ['false', '0', 'n']:
                        return True
                    if str(resp_json.get('status', '')).lower() in ['expired', 'invalid']:
                        return True
                else:
                    # Fallback: scan raw text
                    if any(k in resp_text for k in ['conexão encerrada', 'conexao encerrada', 'logar novamente', 'sessão expirada', 'sessao expirada', 'token inválido', 'token invalido']):
                        return True
                return False

            if is_connection_expired():
                # Invalidate local session and connection data
                try:
                    if hasattr(user, 'validado'):
                        user.validado = False
                    if hasattr(user, 'connection_key'):
                        user.connection_key = None
                    user.save()
                except Exception:
                    # If we cannot save, proceed to logout anyway
                    pass

                logout(request)

                # For fetch/XHR/json requests, return 401 JSON with redirect target
                accepts = request.META.get('HTTP_ACCEPT', '')
                if 'application/json' in accepts or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse(
                        {'error': 'Sessão expirada. Faça login novamente.', 'redirect_url': settings.LOGIN_URL},
                        status=401
                    )
                # For normal browser navigation, redirect to login
                return HttpResponseRedirect(settings.LOGIN_URL)

            # If validation is successful or no expiration detected, optionally refresh user data
            if response.status_code == 200:
                from registration.views import fetch_user_details_from_api
                fetch_user_details_from_api(user)
                
        except Exception as e:
            print(f"Error validating connection: {e}")
        # Continue normal flow
        return None