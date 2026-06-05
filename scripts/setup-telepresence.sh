#!/bin/bash

# One-time initialization script for Telepresence in k3s cluster
set -e

echo "🚀 Initializing Telepresence for k3s cluster..."

# Check if kubectl is configured
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "❌ kubectl is not configured or cluster is not accessible"
    exit 1
fi

echo "✅ Kubernetes cluster is accessible"

# Check if traffic manager is already installed
echo "🔍 Checking for Telepresence traffic manager..."
if kubectl get deployment traffic-manager -n ambassador >/dev/null 2>&1; then
  echo "✅ Traffic manager already installed — applying current agent config"
  telepresence helm upgrade -f "$(dirname "$0")/telepresence-values.yaml"
else
  echo "📦 Installing Telepresence traffic manager..."
  telepresence helm install -f "$(dirname "$0")/telepresence-values.yaml"
  kubectl wait --for=condition=available --timeout=300s deployment/traffic-manager -n ambassador
fi

# Show what was installed
echo ""
echo "📋 Telepresence components in cluster:"
kubectl get all -n ambassador

echo ""
echo "🎉 Telepresence is now ready! You can use:"
echo "  telepresence connect"
echo "  telepresence intercept my-django-app --port 8000:8000"
echo "  python manage.py runserver 0.0.0.0:8000"