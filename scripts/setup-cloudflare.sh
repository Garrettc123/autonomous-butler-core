#!/usr/bin/env bash
# setup-cloudflare.sh — One-time setup for Cloudflare Workers infrastructure
# Usage: bash scripts/setup-cloudflare.sh
set -euo pipefail

WORKERS=(config-bus health-monitor stripe-webhook stripe-poller lead-router)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Creating D1 database: garcar-db"
DB_OUTPUT=$(wrangler d1 create garcar-db 2>&1)
echo "$DB_OUTPUT"
DATABASE_ID=$(echo "$DB_OUTPUT" | grep -oE 'database_id = "[^"]+"' | head -1 | grep -oE '"[^"]+"' | tr -d '"')
if [[ -z "$DATABASE_ID" ]]; then
  echo "ERROR: Could not extract database_id from wrangler output."
  echo "       Re-run after: wrangler d1 list"
  exit 1
fi
echo "    database_id = $DATABASE_ID"

echo ""
echo "==> Creating KV namespaces"

LEADS_KV_OUTPUT=$(wrangler kv namespace create LEADS_KV 2>&1)
echo "$LEADS_KV_OUTPUT"
LEADS_KV_ID=$(echo "$LEADS_KV_OUTPUT" | grep -oE 'id = "[^"]+"' | head -1 | grep -oE '"[^"]+"' | tr -d '"')

CONFIG_KV_OUTPUT=$(wrangler kv namespace create CONFIG_KV 2>&1)
echo "$CONFIG_KV_OUTPUT"
CONFIG_KV_ID=$(echo "$CONFIG_KV_OUTPUT" | grep -oE 'id = "[^"]+"' | head -1 | grep -oE '"[^"]+"' | tr -d '"')

SESSIONS_KV_OUTPUT=$(wrangler kv namespace create SESSIONS_KV 2>&1)
echo "$SESSIONS_KV_OUTPUT"
SESSIONS_KV_ID=$(echo "$SESSIONS_KV_OUTPUT" | grep -oE 'id = "[^"]+"' | head -1 | grep -oE '"[^"]+"' | tr -d '"')

echo ""
echo "    LEADS_KV_ID    = $LEADS_KV_ID"
echo "    CONFIG_KV_ID   = $CONFIG_KV_ID"
echo "    SESSIONS_KV_ID = $SESSIONS_KV_ID"

echo ""
echo "==> Patching wrangler.toml files in all workers"

for WORKER in "${WORKERS[@]}"; do
  TOML="$REPO_ROOT/workers/$WORKER/wrangler.toml"
  if [[ ! -f "$TOML" ]]; then
    echo "    WARN: $TOML not found, skipping"
    continue
  fi
  sed -i "s/REPLACE_WITH_DB_ID/$DATABASE_ID/g"         "$TOML"
  sed -i "s/REPLACE_WITH_LEADS_KV_ID/$LEADS_KV_ID/g"   "$TOML"
  sed -i "s/REPLACE_WITH_CONFIG_KV_ID/$CONFIG_KV_ID/g" "$TOML"
  echo "    patched $TOML"
done

echo ""
echo "==> Running D1 schema migration"
wrangler d1 execute garcar-db --file="$REPO_ROOT/workers/migrations/0001_initial.sql"

echo ""
echo "==> All infrastructure provisioned."
echo ""
echo "======================================================================"
echo "  Next: set the following secrets via wrangler secret put"
echo "  (replace <VALUE> with real values before running)"
echo "======================================================================"
echo ""
for WORKER in "${WORKERS[@]}"; do
  echo "# --- $WORKER ---"
  echo "cd workers/$WORKER"
  echo "wrangler secret put STRIPE_SECRET_KEY        # <VALUE>"
  echo "wrangler secret put STRIPE_WEBHOOK_SECRET    # <VALUE>"
  echo "wrangler secret put OPENAI_API_KEY           # <VALUE>"
  echo "wrangler secret put SLACK_WEBHOOK_URL        # <VALUE>"
  echo "cd ../.."
  echo ""
done
