#!/usr/bin/env bash
# Unprecedented Automater — continuous health + self-heal monitor
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:?}"
SECRETS_FILE="${SECRETS_FILE:-/vault/secrets/.env}"
ALERT_WEBHOOK="${SLACK_WEBHOOK_URL:-}"

check_vault() {
  if ! vault status >/dev/null 2>&1; then
    echo "[$(date -u)] Vault unreachable"
    return 1
  fi
  return 0
}

check_secrets_file() {
  if [[ ! -f "$SECRETS_FILE" ]]; then
    echo "[$(date -u)] Secrets file missing: $SECRETS_FILE"
    return 1
  fi
  # Basic presence checks for critical keys
  for key in ANTHROPIC_API_KEY GITHUB_TOKEN STRIPE_SECRET_KEY; do
    if ! grep -q "^${key}=" "$SECRETS_FILE"; then
      echo "[$(date -u)] Missing critical key: $key"
      return 1
    fi
  done
  return 0
}

alert() {
  local msg="$1"
  echo "$msg"
  if [[ -n "$ALERT_WEBHOOK" ]]; then
    curl -s -X POST -H 'Content-type: application/json' \
      --data "{\"text\":\"[Garcar Vault Automater] $msg\"}" \
      "$ALERT_WEBHOOK" >/dev/null || true
  fi
}

while true; do
  if ! check_vault; then
    alert "Vault unreachable — Agent will retry automatically"
  elif ! check_secrets_file; then
    alert "Secrets file incomplete or missing — check Agent logs"
  else
    echo "[$(date -u)] All systems healthy"
  fi
  sleep 60
done
