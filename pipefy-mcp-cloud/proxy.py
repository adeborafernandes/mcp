"""Proxy OAuth 2.1 (WorkOS AuthKit) na frente do pipefy-mcp-server (HTTP, loopback).

Autenticação aceita:
  1. JWT emitido pelo WorkOS AuthKit (fluxo OAuth do claude.ai / celular / Claude Code),
     restrito a MCP_ALLOWED_EMAILS / MCP_ALLOWED_SUBS.
  2. Opcional: Bearer fixo em MCP_AUTH_TOKEN (ex.: uso via CLI). Deixe vazio para desativar.
"""
import hmac
import logging
import os

import httpx
import jwt
from jwt import PyJWKClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

log = logging.getLogger("proxy")

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:8000")
STATIC_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "").rstrip("/")  # ex.: https://app.fly.dev/mcp
ISSUER = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "").rstrip("/")  # ex.: https://x.authkit.app


def _csv(name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(name, "").split(",") if v.strip()}


ALLOWED_EMAILS = _csv("MCP_ALLOWED_EMAILS")
ALLOWED_SUBS = {v.strip() for v in os.environ.get("MCP_ALLOWED_SUBS", "").split(",") if v.strip()}

# Sem lista de permitidos, qualquer conta do AuthKit entraria: falha fechada.
OAUTH_ENABLED = bool(PUBLIC_URL and ISSUER and (ALLOWED_EMAILS or ALLOWED_SUBS))

_origin = "/".join(PUBLIC_URL.split("/", 3)[:3]) if PUBLIC_URL else ""
AUDIENCES = [a for a in {PUBLIC_URL, _origin, _origin + "/"} if a]
METADATA_URL = (
    f"{_origin}/.well-known/oauth-protected-resource"
    + ("/" + PUBLIC_URL.split("/", 3)[3] if PUBLIC_URL.count("/") >= 3 else "")
    if PUBLIC_URL
    else ""
)

jwks = PyJWKClient(f"{ISSUER}/oauth2/jwks", cache_keys=True) if ISSUER else None

# Headers hop-by-hop / recalculados; origin é removido para não acionar a proteção
# de DNS rebinding do upstream (o acesso já exige autenticação).
DROP_REQ = {"host", "origin", "content-length", "connection", "authorization"}
DROP_RESP = {"content-length", "transfer-encoding", "connection", "content-encoding"}

client = httpx.AsyncClient(base_url=UPSTREAM, timeout=None)


def _unauthorized(desc: str, status: int = 401) -> JSONResponse:
    parts = ['Bearer error="unauthorized"', f'error_description="{desc}"']
    if METADATA_URL:
        parts.append(f'resource_metadata="{METADATA_URL}"')
    return JSONResponse({"error": desc}, status_code=status,
                        headers={"WWW-Authenticate": ", ".join(parts)})


def check_static(token: str) -> bool:
    return bool(STATIC_TOKEN) and hmac.compare_digest(token, STATIC_TOKEN)


def check_jwt(token: str) -> tuple[bool, str]:
    """Valida assinatura/iss/aud/exp e a lista de permitidos. Retorna (ok, motivo)."""
    if not OAUTH_ENABLED or jwks is None:
        return False, "oauth desativado"
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=ISSUER, audience=AUDIENCES,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:  # assinatura, expiração, iss, aud, JWKS inacessível
        log.warning("jwt rejeitado: %s", exc.__class__.__name__)
        return False, "token invalido"
    sub = str(claims.get("sub", ""))
    email = str(claims.get("email", "")).lower()
    if sub in ALLOWED_SUBS or (email and email in ALLOWED_EMAILS):
        return True, ""
    log.warning("usuario nao permitido: sub=%s email=%s", sub, email or "(ausente)")
    return False, "usuario nao permitido"


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


async def resource_metadata(_: Request) -> Response:
    if not OAUTH_ENABLED:
        return JSONResponse({"error": "oauth desativado"}, status_code=404)
    return JSONResponse({
        "resource": PUBLIC_URL,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
    })


async def proxy(request: Request) -> Response:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return _unauthorized("Authorization needed")
    if not check_static(token):
        ok, reason = check_jwt(token)
        if not ok:
            return _unauthorized(reason, 403 if reason == "usuario nao permitido" else 401)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQ}
    upstream_req = client.build_request(
        request.method, request.url.path, params=request.query_params,
        headers=headers, content=await request.body(),
    )
    upstream = await client.send(upstream_req, stream=True)
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in DROP_RESP}
    return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                             headers=resp_headers, background=BackgroundTask(upstream.aclose))


app = Starlette(
    routes=[
        Route("/healthz", health),
        Route("/.well-known/oauth-protected-resource", resource_metadata),
        Route("/.well-known/oauth-protected-resource/{path:path}", resource_metadata),
        Route("/{path:path}", proxy, methods=["GET", "POST", "DELETE", "OPTIONS"]),
    ],
)
