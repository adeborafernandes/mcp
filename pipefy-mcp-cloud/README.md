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

## Segurança / notas
- O proxy valida assinatura (JWKS), `iss`, `aud`, `exp` e a lista de permitidos. O upstream nunca é exposto.
- Perfil `local` do toolkit (o `remote` exige OAuth por requisição): todas as chamadas usam a
  service account, com **todas** as ferramentas. Dê o menor escopo à service account e use
  `PIPEFY_MCP_TOOLSETS` para limitar. Rotacione as credenciais periodicamente.
- O servidor mantém sessão (`mcp-session-id`): rode **1 máquina** no Fly.
- Pacote em pré-release (`0.5.2b1`), por isso `pip install --pre`.
