#!/usr/bin/env bash
# Unprecedented Automater — one-time Vault bootstrap
set -euo pipefail

: "${VAULT_ADDR:?Set VAULT_ADDR}"
: "${VAULT_TOKEN:?Set VAULT_TOKEN (admin)}"

echo "▶ Enabling KV v2 at secret/ (if needed)"
vault secrets enable -path=secret kv-v2 2>/dev/null || true

echo "▶ Writing policies"
vault policy write garcar-github-actions - <<'EOF'
path "secret/data/garcar/*" {
  capabilities = ["read"]
}
path "secret/metadata/garcar/*" {
  capabilities = ["list", "read"]
}
path "secret/metadata/garcar" {
  capabilities = ["list"]
}
EOF

vault policy write garcar-runtime - <<'EOF'
path "secret/data/garcar/*" {
  capabilities = ["read"]
}
path "secret/metadata/garcar/*" {
  capabilities = ["list", "read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

echo "▶ Enabling JWT auth for GitHub OIDC"
vault auth enable jwt 2>/dev/null || true
vault write auth/jwt/config \
  bound_issuer="https://token.actions.githubusercontent.com" \
  oidc_discovery_url="https://token.actions.githubusercontent.com"

vault write auth/jwt/role/garcar-github-actions \
  role_type="jwt" \
  bound_audiences="https://github.com/Garrettc123" \
  bound_claims_type="glob" \
  bound_claims='{"repository":["Garrettc123/autonomous-butler-core","Garrettc123/NEXUS-AI-CORE","Garrettc123/apex-revenue-system","Garrettc123/garcar-payment-loop","Garrettc123/lead-enrichment-engine"]}' \
  user_claim="repository" \
  token_policies="garcar-github-actions" \
  token_ttl="15m" \
  token_max_ttl="30m"

echo "▶ Enabling AppRole for runtime"
vault auth enable approle 2>/dev/null || true
vault write auth/approle/role/garcar-runtime \
  token_policies="garcar-runtime" \
  token_ttl="1h" \
  token_max_ttl="4h" \
  secret_id_ttl="0"

echo "▶ Enabling Kubernetes auth (for Injector)"
vault auth enable kubernetes 2>/dev/null || true
# Note: complete Kubernetes auth config requires cluster CA + token reviewer JWT
# Run the additional commands in vault/automater/k8s/configure-k8s-auth.sh after Injector is installed

echo ""
echo "✅ Bootstrap complete."
echo "Next: write real secrets with vault kv put secret/garcar/<platform> ..."
echo "Then add only VAULT_ADDR to GitHub repository secrets."
