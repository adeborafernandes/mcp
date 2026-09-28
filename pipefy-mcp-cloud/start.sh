#!/bin/sh
set -e
if [ -z "$MCP_AUTH_TOKEN" ] && [ -z "$WORKOS_AUTHKIT_DOMAIN" ]; then echo "Defina WORKOS_AUTHKIT_DOMAIN (OAuth) ou MCP_AUTH_TOKEN" >&2; exit 1; fi

# Upstream apenas em loopback; so o proxy (com Bearer) fica exposto.
export PIPEFY_MCP_TRANSPORT=http
export PIPEFY_MCP_HOST=127.0.0.1
export PIPEFY_MCP_PORT=8000
export PIPEFY_MCP_PROFILE="${PIPEFY_MCP_PROFILE:-local}"

pipefy-mcp-server &
MCP_PID=$!
trap 'kill $MCP_PID 2>/dev/null' EXIT

exec uvicorn proxy:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers
