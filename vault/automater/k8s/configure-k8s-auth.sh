#!/usr/bin/env bash
# Bind Vault Kubernetes auth to the butler-core service account
# Prerequisites: VAULT_ADDR, VAULT_TOKEN, kubectl context pointing at the target cluster
set -euo pipefail

: "${VAULT_ADDR:?Set VAULT_ADDR}"
: "${VAULT_TOKEN:?Set VAULT_TOKEN}"

NAMESPACE="${NAMESPACE:-autonomous-butler}"
SA_NAME="${SA_NAME:-butler-core}"
ROLE_NAME="${ROLE_NAME:-garcar-runtime}"

echo "▶ Gathering Kubernetes auth material..."

# Prefer a dedicated reviewer SA if present; otherwise use the default secret of the butler SA
SECRET_NAME=$(kubectl get sa "$SA_NAME" -n "$NAMESPACE" -o jsonpath='{.secrets[0].name}' 2>/dev/null || true)

if [ -z "$SECRET_NAME" ]; then
  # K8s 1.24+ no longer auto-creates secrets; create a long-lived token
  echo "Creating long-lived token for TokenReview..."
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: butler-core-token
  namespace: $NAMESPACE
  annotations:
    kubernetes.io/service-account.name: $SA_NAME
type: kubernetes.io/service-account-token
EOF
  sleep 2
  SECRET_NAME="butler-core-token"
fi

SA_JWT_TOKEN=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.token}' | base64 -d)
SA_CA_CRT=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.ca\.crt}' | base64 -d)
K8S_HOST=$(kubectl config view --raw --minify --flatten -o jsonpath='{.clusters[].cluster.server}')

echo "▶ Enabling Kubernetes auth method (idempotent)..."
vault auth enable kubernetes 2>/dev/null || true

echo "▶ Writing Kubernetes auth config..."
vault write auth/kubernetes/config \
  token_reviewer_jwt="$SA_JWT_TOKEN" \
  kubernetes_host="$K8S_HOST" \
  kubernetes_ca_cert="$SA_CA_CRT"

echo "▶ Creating / updating role $ROLE_NAME..."
vault write auth/kubernetes/role/"$ROLE_NAME" \
  bound_service_account_names="$SA_NAME" \
  bound_service_account_namespaces="$NAMESPACE" \
  policies="garcar-runtime" \
  ttl="1h" \
  max_ttl="4h"

echo "✅ Kubernetes auth bound:"
echo "   role           = $ROLE_NAME"
echo "   serviceaccount = $NAMESPACE/$SA_NAME"
echo "   policy         = garcar-runtime"
echo ""
echo "Apply the injector-enabled manifests:"
echo "  kubectl apply -f k8s/namespace.yaml"
echo "  kubectl apply -f k8s/serviceaccount.yaml"
echo "  kubectl apply -f k8s/deployment.yaml"
echo "  kubectl apply -f k8s/service.yaml"
echo "  kubectl apply -f k8s/hpa.yaml"
