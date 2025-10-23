import time
import requests
import msal
from django.conf import settings
from django.core.cache import cache

TOKEN_CACHE_KEY = "dyn_app_token"

def get_app_token():
    cached = cache.get(TOKEN_CACHE_KEY)
    if cached and cached.get("expires_at", 0) > time.time() + 30:
        return cached["access_token"]
    app = msal.ConfidentialClientApplication(
        client_id=settings.DYNAMICS_CLIENT_ID,
        client_credential=settings.DYNAMICS_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{settings.DYNAMICS_TENANT_ID}",
    )
    result = app.acquire_token_for_client(scopes=[settings.DYNAMICS_SCOPE])
    token = result["access_token"]
    cache.set(TOKEN_CACHE_KEY, {"access_token": token, "expires_at": time.time() + result["expires_in"] - 30}, result["expires_in"])
    return token

def dyn_get(path, params=None):
    token = get_app_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    }
    url = f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/{path.lstrip('/')}"
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json()
