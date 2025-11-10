import time
import logging
import requests
import msal
from django.conf import settings
from django.core.cache import cache


TOKEN_CACHE_KEY = "dyn_app_token"
logger = logging.getLogger(__name__)

class DynamicsAuthError(Exception):
    pass


def get_app_token():
    cached = cache.get(TOKEN_CACHE_KEY)
    if cached and cached.get("expires_at", 0) > time.time() + 30:
        return cached["access_token"]
    if not settings.DYNAMICS_TENANT_ID or not settings.DYNAMICS_CLIENT_ID or not settings.DYNAMICS_CLIENT_SECRET:
        # Configuration missing; surface a clear error for callers
        logger.error("Dynamics credentials not fully configured (tenant/client/secret)")
        raise DynamicsAuthError("Dynamics credentials are not configured")
    if not settings.DYNAMICS_SCOPE:
        logger.error("Dynamics scope is empty; ensure DYN_ORG_URL is set")
        raise DynamicsAuthError("Dynamics scope is empty; set DYN_ORG_URL")
    app = msal.ConfidentialClientApplication(
        client_id=settings.DYNAMICS_CLIENT_ID,
        client_credential=settings.DYNAMICS_CLIENT_SECRET,
        authority=(
            "https://login.microsoftonline.com/"
            f"{settings.DYNAMICS_TENANT_ID}"
        ),
    )
    result = app.acquire_token_for_client(scopes=[settings.DYNAMICS_SCOPE])
    if "access_token" not in result:
        # Do not log secrets; include safe error metadata
        err = result.get("error")
        desc = result.get("error_description", "")
        logger.error("MSAL token acquisition failed: %s - %s", err, desc)
        raise DynamicsAuthError(
            f"MSAL error: {err}: {desc}"
        )
    token = result["access_token"]
    cache.set(
        TOKEN_CACHE_KEY,
        {
            "access_token": token,
            "expires_at": time.time() + result["expires_in"] - 30,
        },
        result["expires_in"],
    )
    return token


def _headers(include_annotations: bool = False):
    token = get_app_token()
    h = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    }
    if include_annotations:
        h["Prefer"] = (
            "odata.include-annotations="
            "\"OData.Community.Display.V1.FormattedValue\""
        )
    return h


def dyn_get(path, params=None, include_annotations: bool = False):
    url = (
        f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/"
        f"{path.lstrip('/')}"
    )
    try:
        r = requests.get(
            url,
            headers=_headers(include_annotations),
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        body = e.response.text if getattr(e, "response", None) else ""
        logger.error(
            "Dynamics GET %s failed: %s %s", url, getattr(e.response, "status_code", ""), body[:500]
        )
        raise


def dyn_post(path, payload: dict, include_annotations: bool = False):
    url = (
        f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/"
        f"{path.lstrip('/')}"
    )
    headers = {
        **_headers(include_annotations),
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json() if r.content else None
    except requests.HTTPError as e:
        body = e.response.text if getattr(e, "response", None) else ""
        logger.error(
            "Dynamics POST %s failed: %s %s", url, getattr(e, "response", None) and e.response.status_code, body[:500]
        )
        raise


def dyn_patch(path, payload: dict, include_annotations: bool = False):
    url = (
        f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/"
        f"{path.lstrip('/')}"
    )
    headers = {
        **_headers(include_annotations),
        "Content-Type": "application/json",
    }
    try:
        r = requests.patch(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json() if r.content else None
    except requests.HTTPError as e:
        body = e.response.text if getattr(e, "response", None) else ""
        logger.error(
            "Dynamics PATCH %s failed: %s %s", url, getattr(e, "response", None) and e.response.status_code, body[:500]
        )
        raise


def dyn_delete(path):
    url = (
        f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/"
        f"{path.lstrip('/')}"
    )
    try:
        r = requests.delete(url, headers=_headers(False), timeout=20)
        r.raise_for_status()
        return None
    except requests.HTTPError as e:
        body = e.response.text if getattr(e, "response", None) else ""
        logger.error(
            "Dynamics DELETE %s failed: %s %s", url, getattr(e, "response", None) and e.response.status_code, body[:500]
        )
        raise

