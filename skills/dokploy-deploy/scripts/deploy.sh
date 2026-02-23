#!/bin/bash
# Quick deploy script for a project to a remote server via Docker
# Customize the variables below for your environment

set -e

SERVER_IP="${DEPLOY_SERVER_IP:?Set DEPLOY_SERVER_IP}"
APP_DIR="${DEPLOY_APP_DIR:-/opt/myapp}"
PROJECT_DIR="${1:-.}"

echo "🚀 Deploying to ${SERVER_IP}..."

# Sync files to server
echo "📦 Syncing files..."
rsync -avz --exclude 'node_modules' --exclude '__pycache__' \
    "${PROJECT_DIR}/" root@${SERVER_IP}:${APP_DIR}/

# Deploy on server
echo "🔧 Building and starting containers..."
ssh root@${SERVER_IP} << 'ENDSSH'
cd ${APP_DIR}

# Create .env from template if not exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Copy .env.example and configure it."
    exit 1
fi

# Pull and build
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build

echo "Waiting for services to start..."
sleep 10

# Check status
docker-compose -f docker-compose.prod.yml ps
ENDSSH

echo "✅ Deployment complete!"
echo ""
echo "Access your application at: http://${SERVER_IP}"
