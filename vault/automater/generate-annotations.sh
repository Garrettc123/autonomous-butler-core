#!/usr/bin/env bash
# Generate full Kubernetes annotations for every platform
set -euo pipefail

cat <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: butler-core
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "garcar-runtime"
        vault.hashicorp.com/agent-pre-populate: "true"
        vault.hashicorp.com/agent-inject-status: "update"
EOF

platforms=(ai github slack base shopify notion linear supabase wix hubspot apollo docusign google clickup asana stripe enrichment infra)

for p in "${platforms[@]}"; do
  echo "        vault.hashicorp.com/agent-inject-secret-${p}: \"secret/data/garcar/${p}\""
done

echo "        vault.hashicorp.com/agent-inject-template-env: |"
echo "          # Full multi-platform template is in vault/automater/templates/all-platforms.ctmpl"
echo "          # Reference it or inline the needed keys"
