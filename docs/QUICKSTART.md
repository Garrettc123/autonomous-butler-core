# Quick Start Guide

## Prerequisites

### Required
- ✅ **kubectl** - Kubernetes CLI ([install](https://kubernetes.io/docs/tasks/tools/))
- ✅ **Docker** - Container runtime ([install](https://docs.docker.com/get-docker/))
- ✅ **Kubernetes cluster** - Local (minikube/kind) or cloud (EKS/GKE/AKS)

### Optional
- ⚪ **Helm** - NOT required! ([install guide](INSTALL_HELM.md))

## 3 Deployment Options

### Option 1: Docker Compose (Local Dev - Fastest)

**Best for:** Local development and testing

```bash
# 1. Clone repo
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Start
docker-compose up -d

# 4. Verify
curl http://localhost:8000/health
```

✅ **Ready in 2 minutes!**

---

### Option 2: Kubernetes (No Helm Required)

**Best for:** Production without Helm

```bash
# 1. Clone repo
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core

# 2. Configure secrets
cp k8s/secrets.yaml.template k8s/secrets.yaml
# Edit k8s/secrets.yaml with your API keys

# 3. Deploy (one command)
chmod +x deploy-no-helm.sh
./deploy-no-helm.sh

# 4. Access
kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000
curl http://localhost:8000/health
```

✅ **Production-ready without Helm!**

---

### Option 3: Kubernetes with Helm (Optional)

**Best for:** Production with Helm installed

```bash
# 1. Install Helm (if not already installed)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 2. Clone and configure
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core
cp k8s/secrets.yaml.template k8s/secrets.yaml
# Edit secrets

# 3. Deploy with Helm
chmod +x deploy-all.sh
./deploy-all.sh
```

✅ **Full-featured production deployment**

---

## Verification

### Check System Status

```bash
# All pods running?
kubectl get pods -n autonomous-butler

# View logs
kubectl logs -f -n autonomous-butler deployment/butler-core

# Check health
kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000 &
curl http://localhost:8000/health
```

### Test the API

```bash
# Get system status
curl http://localhost:8000/api/butler/status

# Execute a command
curl -X POST http://localhost:8000/api/butler/command \
  -H "Content-Type: application/json" \
  -d '{"text": "Show me system status"}'

# View metrics
curl http://localhost:8000/api/butler/metrics
```

---

## Troubleshooting

### Pods not starting?

```bash
# Describe pod to see errors
kubectl describe pod <pod-name> -n autonomous-butler

# Check events
kubectl get events -n autonomous-butler --sort-by='.lastTimestamp'
```

### Secrets not configured?

```bash
# Check if secrets exist
kubectl get secrets -n autonomous-butler

# Recreate secrets
kubectl delete secret butler-secrets -n autonomous-butler
kubectl apply -f k8s/secrets.yaml
```

### Image pull errors?

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Or use local image
docker build -t ghcr.io/garrettc123/autonomous-butler-core:latest .
kubectl set image deployment/butler-core butler-core=ghcr.io/garrettc123/autonomous-butler-core:latest -n autonomous-butler
```

---

## Next Steps

1. ✅ [Configure monitoring](monitoring.md)
2. ✅ [Set up GitHub webhooks](webhooks.md)
3. ✅ [Configure Stripe integration](stripe.md)
4. ✅ [Add custom agents](agents.md)

---

## Support

- 📖 [Full Documentation](../README.md)
- 🐛 [Report Issues](https://github.com/Garrettc123/autonomous-butler-core/issues)
- 💬 [Discussions](https://github.com/Garrettc123/autonomous-butler-core/discussions)
