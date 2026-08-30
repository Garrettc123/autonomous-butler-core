# Vault Agent Injector — Cluster Bootstrap

## One-time setup

```bash
# 1. Install the Injector (Vault server stays external)
./vault/automater/k8s/install-injector.sh

# 2. Apply service account + RBAC
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccount.yaml

# 3. Bind Kubernetes auth in Vault
export VAULT_ADDR=https://your-vault:8200
export VAULT_TOKEN=hvs.xxxxx
./vault/automater/k8s/configure-k8s-auth.sh

# 4. Deploy with Injector annotations
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

## Patch an already-running Deployment

```bash
kubectl apply -f k8s/serviceaccount.yaml
kubectl patch deployment butler-core -n autonomous-butler --patch-file k8s/vault-injector-patch.yaml
```

## Verify injection

```bash
kubectl describe pod -n autonomous-butler -l app=butler-core
# Look for init container + sidecar named vault-agent-*

kubectl exec -n autonomous-butler deploy/butler-core -c butler-core -- ls -la /vault/secrets
kubectl exec -n autonomous-butler deploy/butler-core -c butler-core -- head -5 /vault/secrets/.env
```

Secrets are rendered by the Injector. No static platform keys remain in Kubernetes Secrets.
