"""Entry point do pipefy-mcp-server com correção gql <-> httpx2.

O gql.transport.httpx faz `import httpx2 as httpx` quando httpx2 existe (o pacote `mcp`
depende dele), mas o auth do Pipefy (pipefy_auth) é construído sobre `httpx.Auth`. As duas
classes são distintas, então o httpx2.AsyncClient rejeita o auth com
`TypeError: Invalid "auth" argument`.

Não aliasar httpx2 -> httpx globalmente: o `mcp` usa APIs próprias do httpx2
(EventSource, ServerSentEvent) e quebraria com ImportError. Redirecionamos só o gql, depois
que toda a cadeia de imports do mcp/pipefy_mcp já rodou com o httpx2 real.
"""
import sys

import httpx

from pipefy_mcp.main import main  # noqa: E402

import gql.transport.httpx as _gql_httpx_transport  # noqa: E402

_gql_httpx_transport.httpx = httpx

if __name__ == "__main__":
    sys.exit(main())
