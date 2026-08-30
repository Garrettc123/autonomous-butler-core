# Full End-to-End HashiCorp Vault Migration Guide

## Goal
Eliminate every static platform secret from GitHub Actions and runtime containers.  
All 14 platforms live exclusively in Vault KV v2. GitHub Actions authenticate via OIDC JWT. Runtime services use AppRole + Vault Agent.

## Prerequisites
- Vault instance (HCP Vault Secrets or self-hosted open-source / Enterprise)
- Admin access to write policies and auth methods
- GitHub repository admin rights (to add the two remaining secrets)

## One-time setup (run once)

```bash
# 1. Set your Vault address
export VAULT_ADDR=https://your-vault.example.com:8200
export VAULT_TOKEN=<root-or-admin-token>

# 2. Bootstrap policies + JWT role
chmod +x vault/setup-commands.sh
./vault/setup-commands.sh

# 3. Write every secret (use the paths in vault/secret-paths.md)
vault kv put secret/garcar/ai ANTHROPIC_API_KEY=... OPENAI_API_KEY=... ...
# ... repeat for all 14 platforms

# 4. Create AppRole credentials for runtime
vault read -field=role_id auth/approle/role/garcar-runtime/role-id > role-id
vault write -f -field=secret_id auth/approle/role/garcar-runtime/secret-id > secret-id
```

## GitHub repository secrets (only these two remain)

| Secret Name       | Value                          |
|-------------------|--------------------------------|
| `VAULT_ADDR`      | https://your-vault...          |
| `VAULT_NAMESPACE` | (optional – HCP/Enterprise)    |

Remove every other platform secret from GitHub Actions settings.

## Verification

1. Go to Actions → “Secrets Validation (Vault)” → Run workflow
2. Confirm every platform smoke test returns green
3. Deploy as normal – the `vault-secrets.yml` job will inject all environment variables before any subsequent steps run

## Runtime (Docker / Kubernetes)

Use the provided `docker-compose.override.yml` + Vault Agent.  
The Agent authenticates with AppRole, writes a short-lived token, and renders a `.env` file that the main container sources.

For Kubernetes, prefer the official Vault Agent Injector or CSI Secrets Store driver with the same AppRole or JWT auth.

## Rollback

If you ever need to fall back, the original `.env.example` still documents every key. Simply re-populate GitHub Actions secrets and remove the Vault steps from the workflows.

---
**This is now the permanent source of truth.** No plaintext platform keys ever leave Vault again.
