# Full-Scale HCP Waypoint Setup Runbook

## 1. HCP Project & Waypoint

1. Create or select an HCP project.
2. Enable **HCP Waypoint**.
3. Connect **HCP Terraform** (or Terraform Cloud) to the same project.
4. Connect GitHub (Garrettc123/autonomous-butler-core) as a VCS provider.

## 2. Terraform modules

Modules live under `waypoint/terraform/`:

| Module | Purpose |
|--------|---------|
| `modules/butler-k8s` | Full K8s deploy (namespace, deployment, HPA, service) with Vault Injector annotations |
| `modules/butler-railway` | Railway service scaffold |
| `modules/vault-binding` | Ensures AppRole / K8s auth role exists for the environment |

## 3. Create Waypoint Templates

In HCP Waypoint UI (or API):

### Template: `butler-production`
- Source: this repo
- Terraform module: `waypoint/terraform/modules/butler-k8s`
- Variables: `environment`, `image_tag`, `replicas`
- Secrets: none static — runtime uses Vault Agent Injector annotations already in the module

### Template: `butler-preview`
- Same module, smaller replica count, short TTL

### Template: `butler-railway`
- Module: `waypoint/terraform/modules/butler-railway`

## 4. Register Actions (Day-2)

Actions trigger existing GitHub workflows so you do **not** duplicate CI logic.

| Action | Trigger |
|--------|---------|
| `deploy` | `workflow_dispatch` on `ci-cd.yml` |
| `validate-secrets` | `workflow_dispatch` on `secrets-validation.yml` |
| `health-check` | `workflow_dispatch` on `integration_health.yml` |
| `destroy` | Terraform destroy via HCP Terraform |

Action definitions are in `waypoint/actions/`.

## 5. Add-ons catalog

Pre-approved infrastructure add-ons developers can attach:

- Stripe revenue stack
- Supabase project binding
- Slack alert channel
- Linear team binding

Defined in `waypoint/addons/`.

## 6. RBAC

- Platform team: create/edit templates & actions
- Developers: use templates, run actions, install add-ons
- No developer ever receives Vault tokens or static platform secrets

## 7. Verification

1. Developer creates app from `butler-production` template
2. Terraform applies K8s manifests with Vault annotations
3. Pod starts → Vault Agent Injector injects secrets
4. Run action `validate-secrets` → green
5. Run action `health-check` → all 14 platforms reachable
