# Template: butler-production

**Purpose**: Full production Autonomous Butler environment.

## Inputs

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| environment | string | production | Environment label |
| image | string | ghcr.io/garrettc123/autonomous-butler-core:latest | Container image |
| replicas | number | 2 | Base replica count |
| namespace | string | autonomous-butler | K8s namespace |

## What gets provisioned

- Kubernetes namespace + Deployment + Service + HPA
- Vault Agent Injector annotations for all critical secret paths
- Service account ready for Kubernetes auth to Vault

## Secrets

**None static.** All 14 platforms are injected at runtime from Vault via the Agent Injector.  
CI secrets are pulled via OIDC JWT (`garcar-github-actions` role).

## Day-2 actions available

- deploy
- validate-secrets
- health-check
- destroy

## Add-ons recommended

- stripe-revenue
- supabase
- slack-alerts
- linear
