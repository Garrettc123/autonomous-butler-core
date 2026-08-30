# Unprecedented Vault Agent Automater

Zero-touch, self-driving secrets system for the entire Garcar 14-platform stack.

## What it does

- Detects runtime (Docker Compose / Kubernetes / GitHub Actions)
- Automatically selects optimal auth + injection method
- Renders every platform secret from `secret/data/garcar/*`
- Continuously renews leases and re-renders secrets
- Self-heals and alerts on Vault unavailability
- Requires zero ongoing human intervention after bootstrap

## Quick Start

```bash
# 1. Bootstrap Vault roles + policies (run once)
./vault/automater/bootstrap.sh

# 2. Write your real secrets into Vault (you do this)
#    See vault/secret-paths.md

# 3. Choose your runtime:

# Docker Compose
docker compose -f docker-compose.yml -f vault/automater/docker-compose.automater.yml up -d

# Kubernetes
kubectl apply -f vault/automater/k8s/
# or patch existing Deployment with generated annotations

# GitHub Actions
# Already wired via vault-secrets.yml + secrets-validation.yml
```

## Architecture

```
Runtime Detection
       │
       ├─ Docker Compose  → Vault Agent sidecar (AppRole)
       ├─ Kubernetes      → Agent Injector annotations (K8s auth)
       └─ GitHub Actions  → hashicorp/vault-action (OIDC JWT)
```

All paths resolve to the same Vault KV structure under `secret/data/garcar/`.
