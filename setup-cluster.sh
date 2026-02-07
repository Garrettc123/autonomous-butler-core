#!/bin/bash
set -e

echo "🔧 Kubernetes Cluster Setup & Configuration"
echo "==========================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl not found${NC}"
    echo "Install: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

echo -e "${GREEN}✅ kubectl installed${NC}"

# Try to connect to existing cluster
echo -e "\n${BLUE}Checking for existing Kubernetes cluster...${NC}"

if kubectl cluster-info &>/dev/null; then
    echo -e "${GREEN}✅ Connected to existing cluster!${NC}"
    kubectl cluster-info
    echo ""
    echo -e "${GREEN}Your cluster is ready!${NC}"
    echo "Run: ./deploy-no-helm.sh"
    exit 0
fi

echo -e "${YELLOW}⚠️  No cluster connection found${NC}"
echo -e "${BLUE}Setting up local Kubernetes cluster...${NC}\n"

# Check what's available
HAS_MINIKUBE=$(command -v minikube &>/dev/null && echo "yes" || echo "no")
HAS_KIND=$(command -v kind &>/dev/null && echo "yes" || echo "no")
HAS_K3D=$(command -v k3d &>/dev/null && echo "yes" || echo "no")
HAS_DOCKER=$(command -v docker &>/dev/null && echo "yes" || echo "no")

echo "Available tools:"
echo "  - minikube: $HAS_MINIKUBE"
echo "  - kind: $HAS_KIND"
echo "  - k3d: $HAS_K3D"
echo "  - docker: $HAS_DOCKER"
echo ""

# Function to setup minikube
setup_minikube() {
    echo -e "${BLUE}Starting minikube cluster...${NC}"
    minikube start --driver=docker --cpus=4 --memory=8192
    kubectl config use-context minikube
    echo -e "${GREEN}✅ Minikube cluster ready!${NC}"
}

# Function to setup kind
setup_kind() {
    echo -e "${BLUE}Creating kind cluster...${NC}"
    kind create cluster --name autonomous-butler
    kubectl config use-context kind-autonomous-butler
    echo -e "${GREEN}✅ Kind cluster ready!${NC}"
}

# Function to setup k3d
setup_k3d() {
    echo -e "${BLUE}Creating k3d cluster...${NC}"
    k3d cluster create autonomous-butler
    kubectl config use-context k3d-autonomous-butler
    echo -e "${GREEN}✅ K3d cluster ready!${NC}"
}

# Try to setup a cluster
if [ "$HAS_MINIKUBE" = "yes" ]; then
    echo -e "${GREEN}Using minikube${NC}"
    setup_minikube
elif [ "$HAS_KIND" = "yes" ]; then
    echo -e "${GREEN}Using kind${NC}"
    setup_kind
elif [ "$HAS_K3D" = "yes" ]; then
    echo -e "${GREEN}Using k3d${NC}"
    setup_k3d
else
    echo -e "${YELLOW}No local Kubernetes tool found. Installing minikube...${NC}"
    
    # Detect OS and install minikube
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
        sudo install minikube-linux-amd64 /usr/local/bin/minikube
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install minikube
    else
        echo -e "${RED}Unsupported OS. Please install manually:${NC}"
        echo "  - minikube: https://minikube.sigs.k8s.io/docs/start/"
        echo "  - kind: https://kind.sigs.k8s.io/docs/user/quick-start/"
        echo "  - k3d: https://k3d.io/"
        exit 1
    fi
    
    setup_minikube
fi

# Verify cluster
echo -e "\n${BLUE}Verifying cluster...${NC}"
kubectl cluster-info
kubectl get nodes

echo -e "\n${GREEN}================================================${NC}"
echo -e "${GREEN}✅ Kubernetes cluster is ready!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Configure secrets: cp k8s/secrets.yaml.template k8s/secrets.yaml"
echo "  2. Deploy system: ./deploy-no-helm.sh"
echo ""
