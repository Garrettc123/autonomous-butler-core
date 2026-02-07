#!/bin/bash
set -e

echo "🚀 Deploying Complete Autonomous Butler System"
echo "================================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
command -v kubectl >/dev/null 2>&1 || { echo "kubectl required"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker required"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "Helm required"; exit 1; }

# Create namespace
echo -e "${BLUE}Creating namespace...${NC}"
kubectl apply -f k8s/namespace.yaml

# Create secrets
echo -e "${BLUE}Creating secrets...${NC}"
if [ ! -f k8s/secrets.yaml ]; then
    echo "Error: k8s/secrets.yaml not found"
    exit 1
fi
kubectl apply -f k8s/secrets.yaml

# Deploy Kafka
echo -e "${BLUE}Deploying Kafka...${NC}"
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install kafka bitnami/kafka --namespace autonomous-butler

# Deploy Redis
echo -e "${BLUE}Deploying Redis...${NC}"
helm install redis bitnami/redis --namespace autonomous-butler --set auth.enabled=false

# Deploy PostgreSQL
echo -e "${BLUE}Deploying PostgreSQL...${NC}"
helm install postgres bitnami/postgresql --namespace autonomous-butler

# Build and push image
echo -e "${BLUE}Building Butler Core image...${NC}"
docker build -t ghcr.io/garrettc123/autonomous-butler-core:latest .
docker push ghcr.io/garrettc123/autonomous-butler-core:latest

# Deploy Butler Core
echo -e "${BLUE}Deploying Butler Core...${NC}"
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# Wait for deployment
echo -e "${BLUE}Waiting for deployment...${NC}"
kubectl rollout status deployment/butler-core -n autonomous-butler --timeout=5m

echo -e "${GREEN}\n✅ Deployment Complete!${NC}"
echo "Access: kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000"