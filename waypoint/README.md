# HCP Waypoint — Full-Scale Integration

Self-service layer on top of the **Vault Automater** + GitHub Actions stack.

Developers request environments from a catalog.  
Platform team owns the golden paths.  
Secrets never leave Vault.

## Architecture

```
Developer (HCP Waypoint UI / API)
        │
        ▼
   Waypoint Template / Action
        │
        ├── Terraform modules (infra)
        │
        ├── GitHub Actions (build/deploy via existing Vault-native workflows)
        │
        └── Vault Agent / Injector (runtime secrets)
```

## Prerequisites

1. Vault Automater already bootstrapped (`./vault/automater/automate-all.sh`)
2. `VAULT_ADDR` set in GitHub repository secrets
3. HCP account with Waypoint enabled
4. HCP Terraform (or TFC) workspace linked to Waypoint

## Quick start

```bash
# 1. Link this repo as the application source in HCP Waypoint
# 2. Create templates from waypoint/templates/
# 3. Register actions from waypoint/actions/
# 4. Developers self-serve from the catalog
```

See `waypoint/SETUP.md` for the full runbook.
