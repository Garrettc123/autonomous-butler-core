#!/usr/bin/env bash
# Run after Vault Agent Injector is installed on the cluster
set -euo pipefail

: "${VAULT_ADDR:?}"
: "${VAULT_TOKEN:?}"

# These values come from the Kubernetes cluster
# SA_JWT_TOKEN=$(kubectl get secret $(kubectl get sa vault-auth -o jsonpath="{.secrets[0].name}") -o jsonpath="{.data.token}" | base64 -d)
# SA_CA_CRT=$(kubectl config view --raw --minify --flatten -o jsonpath='{.clusters[].cluster.certificate-authority-data}' | base64 -d)
# K8S_HOST=$(kubectl config view --raw --minify --flatten -o jsonpath='{.clusters[].cluster.server}')

echo "Configure Kubernetes auth method with your cluster values:"
echo "vault write auth/kubernetes/config \\"
echo "  token_reviewer_jwt=\"\$SA_JWT_TOKEN\" \\"
echo "  kubernetes_host=\"\$K8S_HOST\" \\"
echo "  kubernetes_ca_cert=@/path/to/ca.crt"

echo ""
echo "Then bind the service account:"
echo "vault write auth/kubernetes/role/garcar-runtime \\"
echo "  bound_service_account_names=butler-core \\"
echo "  bound_service_account_namespaces=default \\"
echo "  policies=garcar-runtime \\"
echo "  ttl=1h"
