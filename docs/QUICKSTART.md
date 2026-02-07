# Quick Start Guide

## Prerequisites

### Required
- ✅ **kubectl** - Kubernetes CLI ([install](https://kubernetes.io/docs/tasks/tools/))
- ✅ **Docker** - Container runtime ([install](https://docs.docker.com/get-docker/))
- ✅ **Kubernetes cluster** - We'll help you set this up!

### Optional
- ⚪ **Helm** - NOT required! ([install guide](INSTALL_HELM.md))

---

## Step 0: Set Up Kubernetes Cluster (If Needed)

**Run this first if you get "connection refused" errors:**

```bash
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core

# Auto-detect and setup cluster
chmod +x setup-cluster.sh
./setup-cluster.sh
```

This will:
- ✅ Check for existing cluster
- ✅ Auto-install minikube if needed
- ✅ Start cluster with proper resources
- ✅ Configure kubectl

**Already have a cluster?** Skip to deployment options below.

---

## 3 Deployment Options

### Option 1: Docker Compose (Local Dev - Fastest)

**Best for:** Quick testing without Kubernetes

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

### Option 2: Kubernetes (No Helm Required) ⭐ Recommended

**Best for:** Production deployment

```bash
# 1. Clone repo
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core

# 2. Setup cluster (if needed)
./setup-cluster.sh

# 3. Configure secrets
cp k8s/secrets.yaml.template k8s/secrets.yaml
nano k8s/secrets.yaml  # Add your API keys

# 4. Deploy (one command)
chmod +x deploy-no-helm.sh
./deploy-no-helm.sh

# 5. Access
kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000 &
curl http://localhost:8000/health
```

✅ **Production-ready without Helm!**

---

### Option 3: Kubernetes with Helm (Optional)

**Best for:** If you already have Helm

```bash
# 1. Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 2. Deploy
./deploy-all.sh
```

---

## Troubleshooting

### Error: "connection refused"

```bash
# Run cluster setup
./setup-cluster.sh
```

### Error: "kubectl not found"

```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install kubectl /usr/local/bin/kubectl
```

### Pods not starting?

```bash
# Check what's wrong
kubectl get pods -n autonomous-butler
kubectl describe pod <pod-name> -n autonomous-butler
kubectl logs <pod-name> -n autonomous-butler
```

**Full troubleshooting guide:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Verification

```bash
# All pods running?
kubectl get pods -n autonomous-butler

# Expected output:
# NAME                           READY   STATUS    RESTARTS   AGE
# kafka-0                        1/1     Running   0          2m
# redis-xxx                      1/1     Running   0          2m
# postgres-xxx                   1/1     Running   0          2m
# butler-core-xxx                1/1     Running   0          1m

# Test API
kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000 &
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

---

## Next Steps

1. ✅ [Configure monitoring](monitoring.md)
2. ✅ [Set up GitHub webhooks](webhooks.md)
3. ✅ [Add Stripe integration](stripe.md)
4. ✅ [Create custom agents](agents.md)

---

## Support

- 📖 [Full Documentation](../README.md)
- 🔧 [Troubleshooting Guide](TROUBLESHOOTING.md)
- 🐛 [Report Issues](https://github.com/Garrettc123/autonomous-butler-core/issues)
- 💬 [Discussions](https://github.com/Garrettc123/autonomous-butler-core/discussions)
