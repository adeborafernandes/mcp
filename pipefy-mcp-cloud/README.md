# Pipefy MCP na nuvem (Fly.io)

`pipefy-mcp-server` (HTTP, loopback) + proxy com Bearer token exposto em `/mcp`.

## Deploy
```bash
cd pipefy-mcp-cloud
fly launch --no-deploy --copy-config      # ajuste o nome em fly.toml
fly secrets set \
  MCP_AUTH_TOKEN="$(openssl rand -hex 32)" \
  PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=... \
  PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=...
fly deploy
```

## Conectar
```bash
claude mcp add --transport http pipefy https://SEU-APP.fly.dev/mcp \
  --header "Authorization: Bearer SEU_TOKEN"
```

## Testar
```bash
curl -i https://SEU-APP.fly.dev/healthz                       # 200
curl -i https://SEU-APP.fly.dev/mcp                           # 401
npx @modelcontextprotocol/inspector                           # URL /mcp + header Bearer
```

Obs.: conector personalizado do claude.ai/celular não envia header Bearer fixo;
para isso seria preciso OAuth 2.1 (não incluído aqui).

## Notas
- Perfil `local` do toolkit (o `remote` exige OAuth por requisição). O upstream fica só em
  `127.0.0.1`; apenas o proxy com Bearer é exposto. Isso libera **todas** as ferramentas
  (incluindo as destrutivas) com a sua service account: use `PIPEFY_MCP_TOOLSETS` para limitar.
- O servidor mantém sessão (`mcp-session-id`): rode **1 máquina** no Fly. Se ela parar por
  inatividade, o cliente só precisa reinicializar a sessão.
- Pacote em pré-release (`0.5.2b1`), por isso `pip install --pre`.
