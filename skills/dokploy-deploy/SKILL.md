---
name: "dokploy-deploy"
description: "Deploy applications to Dokploy VPS and push code to GitHub. Use for deployment workflows involving GitHub + Dokploy."
version: "1.0.0"
author: "David Patton"
tags: ["dokploy", "github", "deploy", "docker", "postgresql"]
trigger_patterns:
  - "deploy to dokploy"
  - "push and deploy"
  - "deploy application"
---

# Dokploy & GitHub Deployment Skill

Deploy applications to Dokploy VPS and push code to GitHub.

## Overview

This skill provides tools and procedures for:
1. Pushing code to GitHub repositories
2. Deploying applications to Dokploy self-hosted PaaS
3. Setting up PostgreSQL databases on Dokploy
4. Configuring domains and SSL certificates

## Prerequisites

### Required Secrets
- `GITHUB_PERSONAL_ACCESS_TOKEN` - GitHub PAT with repo permissions
- `DOKPLOY_PRIVATE_KEY` - SSH private key for Dokploy server
- `DOKPLOY_PUBLIC_KEY` - SSH public key (optional)

### Required Variables
- `DOKPLOY_URL` - Dokploy server URL (e.g., http://YOUR_SERVER_IP:3000)

## GitHub Operations

### Create GitHub Repository

```bash
# Using GitHub API
curl -X POST -H "Authorization: token YOUR_GITHUB_TOKEN" \
  https://api.github.com/user/repos \
  -d '{"name":"repo-name","private":true,"auto_init":false}'
```

### Push to GitHub

```bash
# Initialize git if needed
git init
git add -A
git commit -m "Initial commit"

# Add remote and push
git remote add origin https://YOUR_TOKEN@github.com/username/repo-name.git
git branch -M main
git push -u origin main --force
```

## Dokploy Deployment

### Method 1: SSH Direct Deployment

```bash
# Connect to Dokploy server
ssh root@YOUR_SERVER_IP

# Create project directory
mkdir -p /var/lib/dokploy/apps/your-app
cd /var/lib/dokploy/apps/your-app

# Clone or copy project files
# Then use Docker Compose
docker-compose up -d --build
```

### Method 2: GitHub Integration (Recommended)

1. Push code to GitHub repository
2. In Dokploy dashboard:
   - Create new application
   - Connect GitHub repository
   - Configure build settings
   - Deploy

### Method 3: Docker Compose via SSH

```bash
# Copy docker-compose.prod.yml to server
scp docker-compose.prod.yml root@YOUR_SERVER_IP:/opt/studio4/

# SSH and deploy
ssh root@YOUR_SERVER_IP "cd /opt/studio4 && docker-compose -f docker-compose.prod.yml up -d --build"
```

## Database Setup

### PostgreSQL on Dokploy

```bash
# Create PostgreSQL container
docker run -d \
  --name studio4-postgres \
  -e POSTGRES_DB=studio4 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=securepassword \
  -v studio4-pgdata:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:15-alpine

# Initialize schema
docker exec -i studio4-postgres psql -U postgres -d studio4 < schema.sql
```

## Nginx/Domain Configuration

### Reverse Proxy Setup

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
}
```

## Environment Variables

Create `.env` file with:
```
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/studio4
SECRET_KEY=your-secret-key
GEMINI_API_KEY=your-gemini-key
DEBUG=false
```

## Troubleshooting

### Check Container Logs
```bash
docker logs container-name --tail 100 -f
```

### Restart Services
```bash
docker-compose restart
```

### Check Port Binding
```bash
netstat -tlnp | grep :80
```

## Quick Deploy Script

See `scripts/deploy.sh` for automated deployment.
