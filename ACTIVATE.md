# ACTIVATE — Garcar Unprecedented System

**Goal:** Go from zero to full Vault-native + Injector + Waypoint-ready in one sitting.

---

## Prerequisites (you must have these)

| Item | Example |
|------|--------|
| Vault address | `https://vault.example.com:8200` |
| Vault admin token | `hvs.xxxxx` |
| `kubectl` context | pointed at the target cluster |
| `helm` | v3+ |
| GitHub repo admin | to add one secret |

---

## Step 1 — Bootstrap Vault (one command)

```bash
export VAULT_ADDR=https://your-vault:8200
export VAULT_TOKEN=hvs.xxxxx

chmod +x vault/automater/*.sh vault/automater/k8s/*.sh
./vault/automater/automate-all.sh
```

This creates policies, JWT role, AppRole, path structure, and Agent credentials.

---

## Step 2 — Write real secrets (you only)

```bash
# Example for one platform — repeat for all 14
vault kv put secret/garcar/ai \
  ANTHROPIC_API_KEY="sk-ant-..." \
  OPENAI_API_KEY="sk-..." \
  HUGGINGFACE_API_TOKEN="hf_..."

vault kv put secret/garcar/github \
  GITHUB_TOKEN="ghp_..." \
  GITHUB_WEBHOOK_SECRET="$(openssl rand -hex 16)"

vault kv put secret/garcar/stripe \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..."

# Full path list: vault/secret-paths.md
```

**Never** put these values in GitHub, Kubernetes Secrets, or committed files.

---

## Step 3 — One GitHub secret

Repo → Settings → Secrets and variables → Actions → New repository secret:

```
Name:  VAULT_ADDR
Value: https://your-vault:8200
```

(Optional) delete every other platform secret from GitHub.

---

## Step 4 — Kubernetes Injector

```bash
./vault/automater/k8s/install-injector.sh

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccount.yaml

./vault/automater/k8s/configure-k8s-auth.sh

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

Verify:

```bash
kubectl describe pod -n autonomous-butler -l app=butler-core | grep -A5 vault-agent
kubectl exec -n autonomous-butler deploy/butler-core -c butler-core -- head -3 /vault/secrets/.env
```

---

## Step 5 — Prove CI is Vault-native

GitHub → Actions → **Secrets Validation (Vault)** → Run workflow  
GitHub → Actions → **Integration Health Check** → Run workflow

Both must be green.

---

## Step 6 — (Optional) HCP Waypoint

1. Enable HCP Waypoint + link HCP Terraform + connect this GitHub repo.
2. Register templates from `waypoint/templates/`.
3. Register actions from `waypoint/actions/`.
4. Developers self-serve from the catalog.

---

## Done when

- [ ] `automate-all.sh` completed without error
- [ ] Real secrets exist under `secret/data/garcar/*`
- [ ] Only `VAULT_ADDR` remains as a GitHub Actions secret for platforms
- [ ] Injector pods show `vault-agent` init + sidecar
- [ ] `/vault/secrets/.env` is present inside the app container
- [ ] Secrets Validation workflow is green
- [ ] Integration Health Check is green

After that the system is fully autonomous.
