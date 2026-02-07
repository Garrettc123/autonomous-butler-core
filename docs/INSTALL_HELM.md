# Installing Helm (Optional)

Helm is a package manager for Kubernetes. While **not required** for this project (we provide pure Kubernetes manifests), Helm can simplify deployments.

## Why Helm?

- **Simpler deployments** - One command instead of many manifests
- **Version management** - Easy upgrades and rollbacks
- **Configuration** - Parameterized deployments
- **Ecosystem** - 1000+ pre-built charts

## Installation

### macOS
```bash
brew install helm
```

### Linux
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### Windows (PowerShell)
```powershell
choco install kubernetes-helm
```

### From Binary
```bash
# Download latest release
curl -fsSL -o helm.tar.gz https://get.helm.sh/helm-v3.14.0-linux-amd64.tar.gz

# Extract
tar -zxvf helm.tar.gz

# Move to PATH
sudo mv linux-amd64/helm /usr/local/bin/helm

# Verify
helm version
```

## Verify Installation

```bash
helm version
# Should show: version.BuildInfo{Version:"v3.14.0", ...}
```

## Using Helm with Butler

If you have Helm installed, you can use the original `deploy-all.sh` script which deploys using Helm charts:

```bash
./deploy-all.sh
```

Otherwise, use the no-Helm version:

```bash
./deploy-no-helm.sh
```

## Add Useful Helm Repos

```bash
# Bitnami (popular apps)
helm repo add bitnami https://charts.bitnami.com/bitnami

# Prometheus
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts

# Grafana
helm repo add grafana https://grafana.github.io/helm-charts

# Update repos
helm repo update
```

## Deploy with Helm (if installed)

```bash
# Kafka
helm install kafka bitnami/kafka \
  --namespace autonomous-butler \
  --set replicaCount=1

# Redis
helm install redis bitnami/redis \
  --namespace autonomous-butler \
  --set auth.enabled=false

# PostgreSQL
helm install postgres bitnami/postgresql \
  --namespace autonomous-butler \
  --set auth.username=butler \
  --set auth.password=butler \
  --set auth.database=butler
```

## Helm vs. No-Helm Comparison

| Feature | Helm | No-Helm (Pure K8s) |
|---------|------|--------------------|
| **Setup** | Install Helm first | kubectl only |
| **Commands** | Fewer, simpler | More manifests |
| **Flexibility** | High (values.yaml) | Medium (edit YAMLs) |
| **Production** | ✅ Recommended | ✅ Also works |
| **Learning curve** | Steeper | Gentler |

## Conclusion

**You don't need Helm** - use `deploy-no-helm.sh`!

But if you want it for other projects:
- **Development**: Either works fine
- **Production**: Helm recommended for easier management
- **CI/CD**: Helm integrates well with GitOps
