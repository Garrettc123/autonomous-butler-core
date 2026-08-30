#!/usr/bin/env bash
# Install Vault Agent Injector on the cluster (Vault server assumed external)
set -euo pipefail

echo "▶ Adding HashiCorp Helm repo..."
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

echo "▶ Installing / upgrading Vault Agent Injector..."
helm upgrade --install vault hashicorp/vault \
  --namespace vault-system \
  --create-namespace \
  --set "injector.enabled=true" \
  --set "injector.replicas=2" \
  --set "server.enabled=false" \
  --set "ui.enabled=false" \
  --wait

echo "✅ Vault Agent Injector is ready in namespace vault-system"
echo ""
echo "Next: bind Kubernetes auth in Vault:"
echo "  ./vault/automater/k8s/configure-k8s-auth.sh"
