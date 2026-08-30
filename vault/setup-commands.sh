#!/usr/bin/env bash
# One-time Vault bootstrap for Garcar Autonomous Butler
# Run this against your Vault instance (HCP or self-hosted)
set -euo pipefail

export VAULT_ADDR="${VAULT_ADDR:?Set VAULT_ADDR first}"

echo "=== Enabling KV v2 at secret/ ==="
vault secrets enable -path=secret kv-v2 || true

echo "=== Writing policies ==="
vault policy write garcar-github-actions vault/policies/garcar-github-actions.hcl
vault policy write garcar-runtime vault/policies/garcar-runtime.hcl

echo "=== Enabling JWT auth method for GitHub OIDC ==="
vault auth enable jwt || true

vault write auth/jwt/config \
  bound_issuer="https://token.actions.githubusercontent.com" \
  oidc_discovery_url="https://token.actions.githubusercontent.com"

echo "=== Creating GitHub Actions role (bound to your repos) ==="
vault write auth/jwt/role/garcar-github-actions \
  role_type="jwt" \
  bound_audiences="https://github.com/Garrettc123" \
  bound_claims_type="glob" \
  bound_claims='{"repository":"Garrettc123/autonomous-butler-core","repository":"Garrettc123/NEXUS-AI-CORE","repository":"Garrettc123/apex-revenue-system","repository":"Garrettc123/garcar-payment-loop","repository":"Garrettc123/lead-enrichment-engine"}' \
  user_claim="repository" \
  token_policies="garcar-github-actions" \
  token_ttl="15m" \
  token_max_ttl="30m"

echo "=== Creating example AppRole for runtime containers ==="
vault auth enable approle || true
vault write auth/approle/role/garcar-runtime \
  token_policies="garcar-runtime" \
  token_ttl="1h" \
  token_max_ttl="4h" \
  secret_id_ttl="0"

echo "=== Done. Next steps: ==="
echo "1. Write real secrets with: vault kv put secret/garcar/<platform> KEY=value ..."
echo "2. Add only VAULT_ADDR (and optional VAULT_NAMESPACE) to GitHub repo secrets"
echo "3. Run the secrets-validation workflow"
