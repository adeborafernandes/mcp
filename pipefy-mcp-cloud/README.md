# Pipefy MCP na nuvem (Fly.io + login OAuth via WorkOS AuthKit)

`pipefy-mcp-server` (HTTP, só em loopback) + proxy que exige login OAuth 2.1 e expõe `/mcp`.
Funciona no claude.ai (web/desktop/celular), Claude Code e outros clientes MCP.

## 1. WorkOS (dashboard)
1. Crie um projeto e ative **AuthKit**. Anote o domínio: `https://SEU-SUBDOMINIO.authkit.app`.
2. **Connect → Configuration**: ative **Client ID Metadata Document (CIMD)** e também
   **Dynamic Client Registration** (compatibilidade com o claude.ai).
3. Adicione como **Resource Indicator** a URL exata do servidor, ex.: `https://mcp-pipefy.fly.dev/mcp`.
4. Ative login com Google e **MFA**.

## 2. Deploy
```bash
cd pipefy-mcp-cloud
fly launch --no-deploy --copy-config        # ajuste o nome do app em fly.toml
fly secrets set \
  WORKOS_AUTHKIT_DOMAIN=https://SEU-SUBDOMINIO.authkit.app \
  MCP_PUBLIC_URL=https://mcp-pipefy.fly.dev/mcp \
  MCP_ALLOWED_EMAILS=voce@exemplo.com \
  PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=... \
  PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=...
fly deploy
```
Sem `MCP_ALLOWED_EMAILS`/`MCP_ALLOWED_SUBS` o OAuth fica **desativado** (falha fechada).
Se o token não trouxer o claim `email`, veja o `sub` nos logs (`fly logs`, linha
"usuario nao permitido") e ponha em `MCP_ALLOWED_SUBS`.

## 3. Conectar
- **claude.ai / celular:** Configurações → Conectores → Adicionar conector personalizado →
  `https://mcp-pipefy.fly.dev/mcp` → faça login. Uma vez; vale para todos os dispositivos da conta.
- **Claude Code:** `claude mcp add --transport http pipefy https://mcp-pipefy.fly.dev/mcp`
  e autentique via `/mcp`. (Alternativa: `MCP_AUTH_TOKEN` + `--header "Authorization: Bearer ..."`.)

## Testes
```bash
pip install -r requirements.txt pytest && python -m pytest tests
curl -i https://mcp-pipefy.fly.dev/healthz                                   # 200
curl -i https://mcp-pipefy.fly.dev/mcp                                       # 401 + WWW-Authenticate
curl https://mcp-pipefy.fly.dev/.well-known/oauth-protected-resource/mcp     # metadados
```

## Incidentes de produção (e correções já incluídas no código)

**#1 — 403 "usuario nao permitido".** O token do WorkOS pode vir **sem a claim `email`**.
`fly logs` mostra `usuario nao permitido: sub=user_01... email=(ausente)`. Correção, sem novo deploy:
```bash
fly secrets set MCP_ALLOWED_SUBS="user_01XXXXXXXX"
```
Se o provedor não garante `email`, prefira `MCP_ALLOWED_SUBS` desde o início.

**#2 — `TypeError: Invalid "auth" argument` nas chamadas ao Pipefy.** O `gql.transport.httpx`
faz `import httpx2 as httpx` quando `httpx2` existe (o pacote `mcp` depende dele), mas o auth do
Pipefy é construído sobre `httpx.Auth`: classes distintas, o `httpx2.AsyncClient` recusa o objeto.
Aliasar `httpx2 -> httpx` globalmente **não** serve: o `mcp` usa `EventSource`/`ServerSentEvent`
do `httpx2` e falha com `ImportError` no primeiro restart. Correção (em `run_server.py`, usado
por `start.sh`): redirecionar **só** o `gql.transport.httpx` para o `httpx` puro, depois de importar
o `pipefy_mcp`. Depois de qualquer fix de dependências, teste `fly machines restart <id>`.

## Troubleshooting rápido
| Sintoma | Causa provável | Ação |
|---|---|---|
| 401 após o login | Resource Indicator do WorkOS ≠ `MCP_PUBLIC_URL` | Igualar as duas URLs |
| 403 + `usuario nao permitido` | Token sem a claim da allowlist | `MCP_ALLOWED_SUBS` com o `sub` do log |
| `Invalid "auth" argument` | Conflito gql ↔ httpx2 | Usar `run_server.py` |
| `ImportError: EventSource` | Alias global de httpx2 | Redirecionar só o gql |
| Não sobe / credenciais | `PIPEFY_SERVICE_ACCOUNT_*` inválido | Conferir a service account |
| `pip` não acha o pacote | Python < 3.11 | Usar 3.11+ |

## Limitação: máquinas trial do Fly
Sem cartão cadastrado, a máquina para após ~5 min (`Trial machine stopping`) e volta na próxima
requisição (cold start). Cadastrar um cartão elimina isso.

Notas:
- `fly auth login` exige terminal interativo. Em automação, use `fly tokens create` + `FLY_API_TOKEN`.
- Nunca cole `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` em chat/log: use `fly secrets set` no terminal.
- Versões observadas (betas, podem mudar): pipefy-mcp-server 0.5.2b1, mcp 2.0.1, gql 4.4.0,
  httpx 0.28.1, httpx2 2.13.1, httpx-auth 0.23.1. Exige Python ≥ 3.11.

## Segurança / notas
- O proxy valida assinatura (JWKS), `iss`, `aud`, `exp` e a lista de permitidos. O upstream nunca é exposto.
- Perfil `local` do toolkit (o `remote` exige OAuth por requisição): todas as chamadas usam a
  service account, com **todas** as ferramentas. Dê o menor escopo à service account e use
  `PIPEFY_MCP_TOOLSETS` para limitar. Rotacione as credenciais periodicamente.
- O servidor mantém sessão (`mcp-session-id`): rode **1 máquina** no Fly.
- Pacote em pré-release (`0.5.2b1`), por isso `pip install --pre`.

## Gemini Enterprise
O Gemini exige registro manual do cliente OAuth. No WorkOS: **Connect → Applications → OAuth**, redirect
`https://vertexaisearch.cloud.google.com/oauth-redirect`. No formulário do Gemini: Authorization URL
`<AUTHKIT>/oauth2/authorize`, Token URL `<AUTHKIT>/oauth2/token`, Auth URL Parameter
`&resource=<MCP_PUBLIC_URL>`, scopes `openid profile email offline_access`, PKCE ligado.
Se o `fly logs` mostrar `InvalidAudienceError (aud=<client_id> ...)`, o token saiu com a audiência do
cliente: `fly secrets set MCP_EXTRA_AUDIENCES=<client_id>`.
