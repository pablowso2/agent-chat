#!/usr/bin/env bash
set -euo pipefail

# 👇 Pon aquí el directorio que te dio `which npx` (sin /npx al final)
export PATH="/Users/pablosa/.nvm/versions/node/v22.x.x/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
export NODE_TLS_REJECT_UNAUTHORIZED=0

CONSUMER_KEY="diErxZuR6TvL_4U_O3mbs4yTi6Ma"
CONSUMER_SECRET="0FTSVibTfnvm6dufgQy2MacoAc8a"
TOKEN_URL="https://localhost:9443/oauth2/token"
MCP_URL="https://localhost:8243/botibankmcp/1.0/mcp"

TOKEN=$(/usr/bin/curl -sk -u "${CONSUMER_KEY}:${CONSUMER_SECRET}" \
  -d "grant_type=client_credentials" \
  "${TOKEN_URL}" \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "${TOKEN}" ]; then
  echo "No se pudo obtener token de ${TOKEN_URL}" >&2
  exit 1
fi

exec npx mcp-remote "${MCP_URL}" \
  --transport http-only \
  --header "Authorization: Bearer ${TOKEN}"