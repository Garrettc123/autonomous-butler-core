# Troubleshooting Guide

## Error: "connection refused" to localhost:8080

### Problem
```
error validating data: failed to download openapi: Get "http://localhost:8080/openapi/v2?timeout=32s": 
dial tcp 127.0.0.1:8080: connect: connection refused
```

### Cause
kubectl can't connect to a Kubernetes cluster. You need a running cluster.

### Solution

#### Option 1: Automatic Setup (Recommended)
```bash
chmod +x setup-cluster.sh
./setup-cluster.sh
```

This script will:
- ✅ Check for existing cluster
- ✅ Auto-detect minikube/kind/k3d
- ✅ Create cluster if needed
- ✅ Configure kubectl

#### Option 2: Manual Setup

**Using minikube (recommended for local):**
```bash
# Install minikube
# macOS:
brew install minikube

# Linux:
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Start cluster
minikube start --driver=docker --cpus=4 --memory=8192

# Verify
kubectl cluster-info
```

**Using kind:**
```bash
# Install kind
# macOS:
brew install kind

# Linux:
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Create cluster
kind create cluster --name autonomous-butler

# Verify
kubectl cluster-info
```

**Using Docker Desktop (Windows/Mac):**
```bash
# 1. Open Docker Desktop
# 2. Go to Settings → Kubernetes
# 3. Check "Enable Kubernetes"
# 4. Click "Apply & Restart"

# Verify
kubectl config use-context docker-desktop
kubectl cluster-info
```

**Using k3d:**
```bash
# Install k3d
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Create cluster
k3d cluster create autonomous-butler

# Verify
kubectl cluster-info
```

---

## Error: kubectl not found

### Solution

**macOS:**
```bash
brew install kubectl
```

**Linux:**
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

**Windows (PowerShell):**
```powershell
choco install kubernetes-cli
```

---

## Error: Docker not found

### Solution

**All platforms:**
Download from https://docs.docker.com/get-docker/

---

## Error: Pods stuck in "Pending"

### Check Events
```bash
kubectl get events -n autonomous-butler --sort-by='.lastTimestamp'
```

### Common Causes

**1. Not enough resources**
```bash
# Increase minikube resources
minikube stop
minikube start --cpus=4 --memory=8192
```

**2. Storage issues**
```bash
# Check storage
kubectl get pvc -n autonomous-butler

# If storage class missing
kubectl get storageclass
```

---

## Error: ImagePullBackOff

### Solution

**1. Check image name**
```bash
kubectl describe pod <pod-name> -n autonomous-butler | grep Image
```

**2. Use local image (no registry)**
```bash
# Build locally
docker build -t autonomous-butler-core:local .

# For minikube, load image
minikube image load autonomous-butler-core:local

# Update deployment
kubectl set image deployment/butler-core \
  butler-core=autonomous-butler-core:local \
  -n autonomous-butler
```

**3. Use Docker Hub instead**
```bash
# Build and push to Docker Hub
docker build -t YOUR_DOCKERHUB_USERNAME/autonomous-butler-core:latest .
docker push YOUR_DOCKERHUB_USERNAME/autonomous-butler-core:latest

# Update k8s/deployment.yaml:
# image: YOUR_DOCKERHUB_USERNAME/autonomous-butler-core:latest
```

---

## Error: Secrets not found

### Solution
```bash
# Create secrets file
cp k8s/secrets.yaml.template k8s/secrets.yaml

# Edit with your API keys
nano k8s/secrets.yaml

# Apply
kubectl apply -f k8s/secrets.yaml

# Verify
kubectl get secrets -n autonomous-butler
```

---

## Error: Port forward fails

### Solution

**1. Check service exists**
```bash
kubectl get svc -n autonomous-butler
```

**2. Check pods are running**
```bash
kubectl get pods -n autonomous-butler
```

**3. Try different port**
```bash
kubectl port-forward -n autonomous-butler svc/butler-service 9000:8000
curl http://localhost:9000/health
```

---

## Cluster Verification Checklist

```bash
# 1. Cluster reachable?
kubectl cluster-info

# 2. Nodes ready?
kubectl get nodes

# 3. Namespace exists?
kubectl get namespace autonomous-butler

# 4. Pods running?
kubectl get pods -n autonomous-butler

# 5. Services ready?
kubectl get svc -n autonomous-butler

# 6. Secrets configured?
kubectl get secrets -n autonomous-butler

# 7. Logs look good?
kubectl logs -n autonomous-butler deployment/butler-core
```

---

## Complete Reset

If everything is broken, start fresh:

```bash
# Delete namespace (removes everything)
kubectl delete namespace autonomous-butler

# Or delete cluster entirely
minikube delete  # or: kind delete cluster --name autonomous-butler

# Start over
./setup-cluster.sh
./deploy-no-helm.sh
```

---

## Still Stuck?

1. 📖 Check [Quick Start](QUICKSTART.md)
2. 🐛 [Open an issue](https://github.com/Garrettc123/autonomous-butler-core/issues)
3. 💬 [Join discussions](https://github.com/Garrettc123/autonomous-butler-core/discussions)
