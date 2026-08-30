# Unprecedented Vault Agent Automater

**Single command. Full cutover. Zero ongoing intervention.**

```bash
export VAULT_ADDR=https://your-vault:8200
export VAULT_TOKEN=hvs.xxxxx          # admin token, bootstrap only
./vault/automater/automate-all.sh
```

That script:

1. Bootstraps policies + JWT + AppRole + Kubernetes auth roles
2. Generates AppRole credentials for the Agent sidecar
3. Ensures all 14 `secret/garcar/*` paths exist
4. Generates full Kubernetes annotations
5. Prints the exact remaining human steps (write secrets + set VAULT_ADDR in GitHub)

## What is already automated in the repo

| Layer | Status |
|-------|--------|
| Vault policies + auth roles | `automate-all.sh` / `bootstrap.sh` |
| GitHub Actions OIDC → Vault | `ci-cd.yml`, `deploy.yml`, `integration_health.yml`, `vault-secrets.yml`, `secrets-validation.yml` |
| Docker Compose sidecar | `docker-compose.automater.yml` + `agent.hcl` + unified template |
| Kubernetes Injector annotations | `k8s/annotations.yaml` + generator |
| Health monitor + self-heal | `health-monitor.sh` |
| Unified 14-platform template | `templates/all-platforms.ctmpl` |

## Remaining human steps (cannot be automated)

1. **Write real secrets into Vault**  
   `vault kv put secret/garcar/<platform> KEY=value ...`  
   See `vault/secret-paths.md`.

2. **Add one GitHub secret**  
   `VAULT_ADDR` = your Vault URL.

3. (Optional) Delete the old platform secrets from GitHub Actions settings.

After those three actions the entire stack — CI, Docker, Kubernetes — runs with zero static platform secrets and continuous automatic renewal.

## Architecture

```
Runtime Detection
       │
       ├─ Docker Compose  → Vault Agent sidecar (AppRole)
       ├─ Kubernetes      → Agent Injector annotations (K8s auth)
       └─ GitHub Actions  → hashicorp/vault-action (OIDC JWT)
```

All paths resolve to the same Vault KV structure under `secret/data/garcar/`.
