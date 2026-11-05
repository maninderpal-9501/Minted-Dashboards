"""How this server proves who it is to the Ekyam Dev MCP server.

MCP_AUTH_MODE
  oauth    OAuth client credentials (recommended for Ekyam): MCP_OAUTH_CLIENT_ID + MCP_OAUTH_CLIENT_SECRET,
           made once with the backend's /admin/clients. The server swaps them for a short-lived
           access token at the token endpoint (found automatically from the MCP server, or
           MCP_OAUTH_TOKEN_URL) and renews it before it expires.
  api_key  "Authorization: Bearer <EKYAM_MCP_TOKEN>"  (a fixed token the MCP server accepts)
  entra    "Authorization: Bearer <Entra ID token for MCP_ENTRA_SCOPE>" (Azure Managed Identity / az login)
  none     no Authorization header (only for an open server)

The header is added to every HTTP request the MCP client makes. If the MCP server answers 401,
the token is fetched again and the request retried once.
"""
import asyncio
import logging
import time
from urllib.parse import urlsplit

import httpx

from . import config

log = logging.getLogger("minted.auth")


class AuthError(Exception):
    pass


class OAuthClientCredentials:
    def __init__(self) -> None:
        if not (config.MCP_OAUTH_CLIENT_ID and config.MCP_OAUTH_CLIENT_SECRET):
            raise AuthError("MCP_AUTH_MODE=oauth needs MCP_OAUTH_CLIENT_ID and MCP_OAUTH_CLIENT_SECRET")
        self.token_url = config.MCP_OAUTH_TOKEN_URL
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def _discover(self, c: httpx.AsyncClient) -> str:
        """MCP server -> its authorization server -> token endpoint (RFC 9728 / RFC 8414)."""
        u = urlsplit(config.MCP_URL)
        origin = f"{u.scheme}://{u.netloc}"
        auth_server = origin
        try:
            r = await c.get(origin + "/.well-known/oauth-protected-resource")
            if r.status_code == 200 and r.json().get("authorization_servers"):
                auth_server = r.json()["authorization_servers"][0].rstrip("/")
        except Exception:
            pass
        for path in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
            try:
                r = await c.get(auth_server + path)
                if r.status_code == 200 and r.json().get("token_endpoint"):
                    log.info("OAuth token endpoint: %s", r.json()["token_endpoint"])
                    return r.json()["token_endpoint"]
            except Exception:
                continue
        raise AuthError(f"Could not find the OAuth token endpoint at {auth_server}; set MCP_OAUTH_TOKEN_URL")

    async def _fetch(self) -> None:
        async with httpx.AsyncClient(timeout=30) as c:
            if not self.token_url:
                self.token_url = await self._discover(c)
            form = {"grant_type": "client_credentials"}
            if config.MCP_OAUTH_SCOPE:
                form["scope"] = config.MCP_OAUTH_SCOPE
            # client_secret_post first, then HTTP Basic (servers accept one or the other)
            r = await c.post(self.token_url, data={**form, "client_id": config.MCP_OAUTH_CLIENT_ID,
                                                   "client_secret": config.MCP_OAUTH_CLIENT_SECRET})
            if r.status_code in (400, 401):
                r2 = await c.post(self.token_url, data=form,
                                  auth=(config.MCP_OAUTH_CLIENT_ID, config.MCP_OAUTH_CLIENT_SECRET))
                if r2.status_code == 200:
                    r = r2
            if r.status_code != 200:
                raise AuthError(f"OAuth token request failed ({r.status_code}): {r.text[:300]}")
            body = r.json()
        if not body.get("access_token"):
            raise AuthError(f"OAuth token response had no access_token: {str(body)[:300]}")
        self._token = body["access_token"]
        self._expires = time.time() + float(body.get("expires_in", 3600))
        log.info("OAuth access token obtained (valid %ss, scope %s)", body.get("expires_in", "?"), body.get("scope", "?"))

    async def token(self, force: bool = False) -> str:
        async with self._lock:
            if force or not self._token or time.time() > self._expires - 120:  # renew 2 minutes early
                await self._fetch()
            return self._token


class ServiceAuth(httpx.Auth):
    def __init__(self) -> None:
        self.mode = config.MCP_AUTH_MODE
        self._cred = None
        self._oauth = None
        if self.mode == "oauth":
            self._oauth = OAuthClientCredentials()
        elif self.mode == "entra":
            if not config.MCP_ENTRA_SCOPE:
                raise AuthError("MCP_AUTH_MODE=entra needs MCP_ENTRA_SCOPE (e.g. api://ekyam-tools/.default)")
            from azure.identity.aio import DefaultAzureCredential  # only needed in entra mode
            self._cred = DefaultAzureCredential()
        elif self.mode == "api_key":
            if not config.MCP_TOKEN:
                raise AuthError("MCP_AUTH_MODE=api_key needs EKYAM_MCP_TOKEN")
        elif self.mode != "none":
            raise AuthError("MCP_AUTH_MODE must be oauth, api_key, entra or none")

    async def _token(self, force: bool = False) -> str | None:
        if self.mode == "oauth":
            return await self._oauth.token(force)
        if self.mode == "entra":
            return (await self._cred.get_token(config.MCP_ENTRA_SCOPE)).token
        if self.mode == "api_key":
            return config.MCP_TOKEN
        return None

    async def async_auth_flow(self, request):
        token = await self._token()
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401 and self.mode in ("oauth", "entra"):
            # token revoked or expired early: get a fresh one and retry once
            await response.aread()
            request.headers["Authorization"] = f"Bearer {await self._token(force=True)}"
            yield request

    def sync_auth_flow(self, request):
        if self.mode == "api_key":
            request.headers["Authorization"] = f"Bearer {config.MCP_TOKEN}"
        yield request

    async def close(self) -> None:
        if self._cred is not None:
            await self._cred.close()
