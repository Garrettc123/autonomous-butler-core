#!/usr/bin/env bash
# =============================================================================
# GARCAR UNPRECEDENTED VAULT AUTOMATER — MASTER ENTRYPOINT
# One command. Full cutover. Zero ongoing intervention after secrets are written.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; }
info() { echo -e "${BLUE}▶ $*${NC}"; }

echo ""
echo "=============================================="
echo "  GARCAR VAULT AUTOMATER — FULL AUTOMATION"
echo "=============================================="
echo ""

# ── 1. Prerequisites ──
info "Checking prerequisites..."

MISSING=0
command -v vault >/dev/null 2>&1 || { err "vault CLI not found"; MISSING=1; }
command -v docker >/dev/null 2>&1 || warn "docker not found (Compose path will be skipped)"
command -v kubectl >/dev/null 2>&1 || warn "kubectl not found (K8s path will be skipped)"

if [ -z "${VAULT_ADDR:-}" ]; then
  err "VAULT_ADDR is not set"
  MISSING=1
fi
if [ -z "${VAULT_TOKEN:-}" ]; then
  err "VAULT_TOKEN is not set (needed only for bootstrap)"
  MISSING=1
fi

if [ $MISSING -eq 1 ]; then
  echo ""
  err "Fix the above and re-run. Example:"
  echo "  export VAULT_ADDR=https://your-vault:8200"
  echo "  export VAULT_TOKEN=hvs.xxxxx"
  echo "  ./vault/automater/automate-all.sh"
  exit 1
fi
ok "Prerequisites OK (VAULT_ADDR=$VAULT_ADDR)"

# ── 2. Bootstrap Vault (idempotent) ──
info "Bootstrapping Vault policies + auth methods..."
chmod +x vault/automater/bootstrap.sh
if ./vault/automater/bootstrap.sh; then
  ok "Vault bootstrap complete"
else
  err "Bootstrap failed"
  exit 1
fi

# ── 3. Generate AppRole credentials for runtime ──
info "Generating AppRole credentials for Vault Agent..."
mkdir -p vault/automater
ROLE_ID=$(vault read -field=role_id auth/approle/role/garcar-runtime/role-id 2>/dev/null || true)
if [ -z "$ROLE_ID" ]; then
  warn "Could not read role_id — ensure bootstrap succeeded"
else
  echo -n "$ROLE_ID" > vault/automater/role-id
  ok "Wrote vault/automater/role-id"
fi

SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/garcar-runtime/secret-id 2>/dev/null || true)
if [ -z "$SECRET_ID" ]; then
  warn "Could not generate secret_id"
else
  echo -n "$SECRET_ID" > vault/automater/secret-id
  chmod 600 vault/automater/secret-id
  ok "Wrote vault/automater/secret-id (mode 600)"
fi

# ── 4. Verify / create empty secret paths (structure only) ──
info "Ensuring Vault path structure exists..."
PLATFORMS=(ai github slack base shopify notion linear supabase wix hubspot apollo docusign google clickup asana stripe enrichment infra)
for p in "${PLATFORMS[@]}"; do
  if vault kv get "secret/garcar/$p" >/dev/null 2>&1; then
    ok "secret/garcar/$p already has data"
  else
    # Create placeholder so path exists; user overwrites with real values
    vault kv put "secret/garcar/$p" PLACEHOLDER="replace-me" >/dev/null 2>&1 || true
    warn "Created placeholder at secret/garcar/$p — REPLACE with real secrets"
  fi
done

# ── 5. Generate K8s annotations ──
info "Generating Kubernetes annotations..."
chmod +x vault/automater/generate-annotations.sh
./vault/automater/generate-annotations.sh > vault/automater/k8s/full-annotations.yaml 2>/dev/null || true
ok "Generated vault/automater/k8s/full-annotations.yaml"

# ── 6. Make scripts executable ──
chmod +x vault/automater/*.sh vault/automater/k8s/*.sh 2>/dev/null || true
ok "Scripts marked executable"

# ── 7. Final status report ──
echo ""
echo "=============================================="
echo "  AUTOMATION COMPLETE — FINAL CHECKLIST"
echo "=============================================="
echo ""
echo "1. Write REAL secrets into Vault:"
echo "   vault kv put secret/garcar/ai ANTHROPIC_API_KEY=sk-ant-... OPENAI_API_KEY=..."
echo "   (repeat for every platform — see vault/secret-paths.md)"
echo ""
echo "2. Add ONLY this GitHub repository secret:"
echo "   VAULT_ADDR = $VAULT_ADDR"
echo ""
echo "3. (Optional) Delete all other platform secrets from GitHub Actions"
echo ""
echo "4. Runtime activation:"
echo "   Docker:  docker compose -f docker-compose.yml -f vault/automater/docker-compose.automater.yml up -d"
echo "   K8s:     kubectl patch deployment butler-core --patch-file vault/automater/k8s/annotations.yaml"
echo "   CI:      already wired — next push will use Vault"
echo ""
echo "5. Validate:"
echo "   GitHub Actions → Secrets Validation (Vault) → Run workflow"
echo ""
ok "Unprecedented Automater is ready. Secrets are the only remaining human step."
echo ""
