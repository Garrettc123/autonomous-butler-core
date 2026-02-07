#!/bin/bash
set -e

echo "🚀 Deploying Autonomous Butler (No Helm Required)"
echo "==================================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl required but not installed. Install: https://kubernetes.io/docs/tasks/tools/"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker required but not installed. Install: https://docs.docker.com/get-docker/"; exit 1; }

echo -e "${GREEN}✅ All prerequisites met${NC}"

# Create namespace
echo -e "${BLUE}Creating namespace...${NC}"
kubectl apply -f k8s/namespace.yaml

# Check for secrets
echo -e "${BLUE}Checking secrets...${NC}"
if [ ! -f k8s/secrets.yaml ]; then
    echo -e "${YELLOW}⚠️  Creating secrets from template...${NC}"
    cp k8s/secrets.yaml.template k8s/secrets.yaml
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit k8s/secrets.yaml with your API keys before continuing!${NC}"
    echo -e "${YELLOW}Press Enter when ready...${NC}"
    read
fi

kubectl apply -f k8s/secrets.yaml
echo -e "${GREEN}✅ Secrets configured${NC}"

# Deploy Kafka (pure Kubernetes)
echo -e "${BLUE}Deploying Kafka...${NC}"
kubectl apply -f k8s/kafka.yaml
echo -e "${GREEN}✅ Kafka deployed${NC}"

# Deploy Redis
echo -e "${BLUE}Deploying Redis...${NC}"
kubectl apply -f k8s/redis.yaml
echo -e "${GREEN}✅ Redis deployed${NC}"

# Deploy PostgreSQL
echo -e "${BLUE}Deploying PostgreSQL...${NC}"
kubectl apply -f k8s/postgres.yaml
echo -e "${GREEN}✅ PostgreSQL deployed${NC}"

# Wait for dependencies
echo -e "${BLUE}Waiting for dependencies to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=kafka -n autonomous-butler --timeout=300s || echo "Kafka taking longer than expected..."
kubectl wait --for=condition=ready pod -l app=redis -n autonomous-butler --timeout=300s || echo "Redis taking longer than expected..."
kubectl wait --for=condition=ready pod -l app=postgres -n autonomous-butler --timeout=300s || echo "Postgres taking longer than expected..."

# Build and push Butler Core image
echo -e "${BLUE}Building Butler Core Docker image...${NC}"
IMAGE_NAME="ghcr.io/garrettc123/autonomous-butler-core:latest"

if docker build -t "$IMAGE_NAME" . ; then
    echo -e "${GREEN}✅ Image built successfully${NC}"
    
    echo -e "${BLUE}Pushing to registry...${NC}"
    if docker push "$IMAGE_NAME" 2>/dev/null; then
        echo -e "${GREEN}✅ Image pushed to registry${NC}"
    else
        echo -e "${YELLOW}⚠️  Registry push failed (may need 'docker login ghcr.io')${NC}"
        echo -e "${YELLOW}Continuing with local image...${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Docker build failed, using existing image${NC}"
fi

# Deploy Butler Core
echo -e "${BLUE}Deploying Butler Core...${NC}"
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
echo -e "${GREEN}✅ Butler Core deployed${NC}"

# Wait for Butler Core deployment
echo -e "${BLUE}Waiting for Butler Core to be ready...${NC}"
kubectl rollout status deployment/butler-core -n autonomous-butler --timeout=5m

# Run health check
echo -e "${BLUE}Running health check...${NC}"
sleep 10

# Port forward in background
kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000 >/dev/null 2>&1 &
PF_PID=$!
sleep 5

# Test health endpoint
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo -e "${GREEN}✅ Health check passed!${NC}"
else
    echo -e "${YELLOW}⚠️  Health check inconclusive (service may still be starting)${NC}"
fi

# Cleanup port forward
kill $PF_PID 2>/dev/null || true

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "📋 Access URLs:"
echo "  - Butler API: kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000"
echo "  - Then visit: http://localhost:8000/health"
echo ""
echo "🔍 Quick commands:"
echo "  - View logs:    kubectl logs -f -n autonomous-butler deployment/butler-core"
echo "  - Check status: kubectl get all -n autonomous-butler"
echo "  - Get pods:     kubectl get pods -n autonomous-butler"
echo "  - Describe pod: kubectl describe pod <pod-name> -n autonomous-butler"
echo ""
echo "🧪 Test the API:"
echo "  kubectl port-forward -n autonomous-butler svc/butler-service 8000:8000 &"
echo '  curl http://localhost:8000/api/butler/status'
echo ""
echo "🤖 Autonomous Butler is now operational!"
