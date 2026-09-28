"""Proxy com Bearer token na frente do pipefy-mcp-server (HTTP, localhost)."""
import hmac
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:8000")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

# Headers hop-by-hop / que devem ser recalculados; origin é removido para não
# acionar a proteção de DNS rebinding do upstream (o acesso já exige token).
DROP_REQ = {"host", "origin", "content-length", "connection", "authorization"}
DROP_RESP = {"content-length", "transfer-encoding", "connection", "content-encoding"}

client = httpx.AsyncClient(base_url=UPSTREAM, timeout=None)


def authorized(request: Request) -> bool:
    if not AUTH_TOKEN:
        return False
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(token, AUTH_TOKEN)


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


async def proxy(request: Request) -> Response:
    if not authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401,
                            headers={"WWW-Authenticate": "Bearer"})

    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQ}
    upstream_req = client.build_request(
        request.method,
        request.url.path,
        params=request.query_params,
        headers=headers,
        content=await request.body(),
    )
    upstream = await client.send(upstream_req, stream=True)
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in DROP_RESP}
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=resp_headers,
        background=None,
    )


app = Starlette(
    routes=[
        Route("/healthz", health),
        Route("/{path:path}", proxy, methods=["GET", "POST", "DELETE", "OPTIONS"]),
    ],
)
