# Ironclaw Production Deployment Guide

This guide covers deploying Ironclaw to production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Options](#deployment-options)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Configuration](#configuration)
6. [Security](#security)
7. [Monitoring](#monitoring)
8. [Backup & Recovery](#backup--recovery)

## Prerequisites

### Hardware Requirements

**Minimum (Development)**:
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB SSD

**Recommended (Production)**:
- CPU: 4-8 cores
- RAM: 16-32GB
- Storage: 100GB SSD

**Optimized for Acer Swift Neo**:
- Intel Core Ultra with NPU
- 16GB RAM
- 512GB SSD

### Software Requirements

- **Docker**: 24.0+
- **Docker Compose**: 2.20+
- **Kubernetes**: 1.24+ (for K8s deployment)
- **Python**: 3.11+
- **PostgreSQL**: 15+
- **Redis**: 7+

## Deployment Options

### Option 1: Docker Compose (Recommended for small deployments)

Best for:
- Single server deployments
- Development/staging environments
- Quick prototyping

### Option 2: Kubernetes (Recommended for production)

Best for:
- Multi-server deployments
- High availability requirements
- Auto-scaling needs
- Enterprise production

## Docker Deployment

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/ironclaw.git
cd ironclaw
```

### Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
nano .env
```

**Required Environment Variables**:

```env
# Security
SECRET_KEY=your-super-secret-key-min-32-chars
JWT_SECRET_KEY=your-jwt-secret-key-min-32-chars

# Database
POSTGRES_PASSWORD=your-postgres-password
REDIS_PASSWORD=your-redis-password

# AI Providers (at least one required)
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# Optional
SENTRY_DSN=https://...@sentry.io/...
```

### Step 3: Start Services

**Development**:
```bash
docker-compose up -d
```

**Production**:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Step 4: Verify Deployment

```bash
# Check services
docker-compose ps

# Check logs
docker-compose logs -f ironclaw-api

# Test API
curl http://localhost:8000/health
```

### Step 5: Scale Services (Production)

```bash
# Scale API to 4 instances
docker-compose -f docker-compose.prod.yml up -d --scale ironclaw-api=4
```

## Kubernetes Deployment

### Step 1: Prerequisites

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Verify cluster access
kubectl cluster-info
```

### Step 2: Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### Step 3: Configure Secrets

```bash
# Edit k8s/secret.yaml with your actual secrets
nano k8s/secret.yaml

# Apply secrets
kubectl apply -f k8s/secret.yaml
```

### Step 4: Deploy Infrastructure

```bash
# Apply all K8s manifests
kubectl apply -f k8s/

# OR apply individually
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/ingress.yaml
```

### Step 5: Verify Deployment

```bash
# Check pods
kubectl get pods -n ironclaw

# Check services
kubectl get svc -n ironclaw

# Check ingress
kubectl get ingress -n ironclaw

# View logs
kubectl logs -f -n ironclaw -l app=ironclaw-api

# Port forward for testing
kubectl port-forward -n ironclaw svc/ironclaw-api 8000:8000
```

### Step 6: Configure DNS & TLS

```bash
# Install cert-manager for TLS
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Update ingress with your domain
nano k8s/ingress.yaml
kubectl apply -f k8s/ingress.yaml
```

## Configuration

### Production Environment Variables

```env
# Environment
ENVIRONMENT=production
DEBUG=false

# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Performance
MAX_CONCURRENT_REQUESTS=100
REQUEST_TIMEOUT_SECONDS=120
MAX_MEMORY_MB=8192

# Monitoring
ENABLE_PROMETHEUS=true
ENABLE_OPENTELEMETRY=true
ENABLE_SENTRY=true
LOG_LEVEL=INFO

# Security
ENABLE_AUTHENTICATION=true
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60
```

### Database Configuration

**PostgreSQL**:
```env
DATABASE_URL=postgresql+asyncpg://ironclaw:password@postgres:5432/ironclaw_db
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

**Redis**:
```env
REDIS_URL=redis://:password@redis:6379/0
REDIS_MAX_CONNECTIONS=50
REDIS_CACHE_TTL=3600
```

## Security

### 1. Generate Strong Secrets

```bash
# Generate 32-character secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Enable HTTPS

**For Docker**:
- Configure nginx with SSL certificates
- Use Let's Encrypt for free certificates

**For Kubernetes**:
- Install cert-manager
- Configure TLS in Ingress

### 3. Network Security

```bash
# Docker: Use internal networks
# Kubernetes: Use NetworkPolicies

kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ironclaw-network-policy
  namespace: ironclaw
spec:
  podSelector:
    matchLabels:
      app: ironclaw-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector: {}
  egress:
  - to:
    - podSelector: {}
EOF
```

### 4. Secrets Management

**Use Kubernetes Secrets** (production):
```bash
kubectl create secret generic ironclaw-secrets \
  --from-literal=SECRET_KEY=xxx \
  --from-literal=POSTGRES_PASSWORD=yyy \
  --namespace=ironclaw
```

**Or use external secrets manager**:
- AWS Secrets Manager
- HashiCorp Vault
- Azure Key Vault

## Monitoring

### Access Monitoring Tools

**Prometheus**:
```bash
# Docker
http://localhost:9090

# Kubernetes
kubectl port-forward -n ironclaw svc/prometheus 9090:9090
```

**Grafana**:
```bash
# Docker
http://localhost:3001

# Kubernetes
kubectl port-forward -n ironclaw svc/grafana 3000:3000
```

**Jaeger** (Distributed Tracing):
```bash
http://localhost:16686
```

### Key Metrics to Monitor

1. **API Performance**:
   - Request rate
   - Error rate
   - Latency (p50, p95, p99)

2. **Resources**:
   - CPU usage
   - Memory usage
   - Disk I/O

3. **AI Providers**:
   - Request count
   - Cost tracking
   - Error rates

## Backup & Recovery

### Database Backups

**PostgreSQL**:
```bash
# Backup
docker exec ironclaw-postgres pg_dump -U ironclaw ironclaw_db > backup.sql

# Restore
docker exec -i ironclaw-postgres psql -U ironclaw ironclaw_db < backup.sql
```

**Automated Backups**:
```bash
# Add to crontab
0 2 * * * docker exec ironclaw-postgres pg_dump -U ironclaw ironclaw_db | gzip > /backups/ironclaw_$(date +\%Y\%m\%d).sql.gz
```

### Disaster Recovery

1. **Backup Strategy**:
   - Daily database backups
   - Weekly full system backups
   - Retain backups for 30 days

2. **Recovery Procedure**:
   ```bash
   # Stop services
   docker-compose down
   
   # Restore database
   docker-compose up -d postgres
   docker exec -i ironclaw-postgres psql -U ironclaw ironclaw_db < backup.sql
   
   # Restart all services
   docker-compose up -d
   ```

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues and solutions.

## Next Steps

- [Configure Monitoring](./MONITORING.md)
- [Performance Tuning](./PERFORMANCE_TUNING.md)
- [Security Best Practices](./SECURITY.md)
