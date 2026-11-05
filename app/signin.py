"""Minimal sign-in for local testing and private demos.

MINTED_DEMO_KEY empty  -> everyone is let in (local testing).
MINTED_DEMO_KEY set    -> open any page once with ?key=<value>; a cookie keeps you signed in.

Replace with real sign-in (Ekyam SSO / Entra ID Easy Auth in Azure) before a public deployment:
only `current_user` needs to change.
"""
import hmac

from fastapi import HTTPException, Request

from . import config

COOKIE = "minted_key"


def is_signed_in(request: Request) -> bool:
    if not config.DEMO_KEY:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), config.DEMO_KEY)


def current_user(request: Request) -> str:
    """FastAPI dependency for API routes: 401 if not signed in (the pages show a sign-in message)."""
    if not is_signed_in(request):
        raise HTTPException(401, "Not signed in")
    # Azure App Service Easy Auth puts the signed-in user here; handy once you switch it on.
    return request.headers.get("x-ms-client-principal-name", "local-user")
