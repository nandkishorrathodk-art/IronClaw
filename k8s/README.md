# Ironclaw Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Ironclaw in production.

## Prerequisites

- Kubernetes cluster 1.24+
- kubectl configured
- NGINX Ingress Controller
- cert-manager (for TLS certificates)
- Storage provisioner (for PVCs)

## Quick Start

### 1. Create Namespace

```bash
kubectl apply -f namespace.yaml
```

### 2. Configure Secrets

Edit `secret.yaml` with your actual secrets:

```bash
kubectl apply -f secret.yaml
```

### 3. Apply Configuration

```bash
kubectl apply -f configmap.yaml
```

### 4. Create Persistent Volumes

```bash
kubectl apply -f pvc.yaml
```

### 5. Deploy Services

```bash
kubectl apply -f service.yaml
```

### 6. Deploy Application

```bash
kubectl apply -f deployment.yaml
```

### 7. Configure Autoscaling

```bash
kubectl apply -f hpa.yaml
```

### 8. Set Up Ingress

Edit `ingress.yaml` with your domain and apply:

```bash
kubectl apply -f ingress.yaml
```

## Full Deployment (All-in-One)

```bash
kubectl apply -f .
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n ironclaw

# Check services
kubectl get svc -n ironclaw

# Check ingress
kubectl get ingress -n ironclaw

# Check HPA
kubectl get hpa -n ironclaw

# View logs
kubectl logs -f -n ironclaw -l app=ironclaw-api

# Get pod details
kubectl describe pod -n ironclaw <pod-name>
```

## Scaling

### Manual Scaling

```bash
kubectl scale deployment ironclaw-api -n ironclaw --replicas=5
```

### Autoscaling

HPA is configured to scale between 3-10 replicas based on CPU (70%) and Memory (80%) usage.

## Rolling Updates

```bash
# Update image
kubectl set image deployment/ironclaw-api ironclaw-api=ironclaw-api:v2 -n ironclaw

# Check rollout status
kubectl rollout status deployment/ironclaw-api -n ironclaw

# Rollback if needed
kubectl rollout undo deployment/ironclaw-api -n ironclaw
```

## Monitoring

```bash
# View metrics
kubectl top pods -n ironclaw
kubectl top nodes

# Port forward to access Prometheus
kubectl port-forward -n ironclaw svc/prometheus 9090:9090

# Port forward to access Grafana
kubectl port-forward -n ironclaw svc/grafana 3000:3000
```

## Troubleshooting

```bash
# Check events
kubectl get events -n ironclaw --sort-by='.lastTimestamp'

# Debug pod
kubectl exec -it -n ironclaw <pod-name> -- /bin/sh

# View logs
kubectl logs -n ironclaw <pod-name> --previous  # Previous container logs
kubectl logs -n ironclaw <pod-name> -c <container-name>  # Specific container
```

## Resource Quotas

Current configuration:
- **API Pods**: 2-4Gi memory, 1-2 CPU cores
- **Min Replicas**: 3
- **Max Replicas**: 10
- **Storage**: 
  - Data: 10Gi
  - Postgres: 20Gi
  - Redis: 5Gi
  - Qdrant: 10Gi

## Production Checklist

- [ ] Update all secrets in `secret.yaml`
- [ ] Configure domain in `ingress.yaml`
- [ ] Set up TLS certificates with cert-manager
- [ ] Configure backup strategy for PVCs
- [ ] Set up monitoring and alerting
- [ ] Configure log aggregation
- [ ] Set resource limits appropriately
- [ ] Configure network policies
- [ ] Enable pod security policies
- [ ] Set up disaster recovery plan

## Clean Up

```bash
kubectl delete namespace ironclaw
```

Note: This will delete all resources in the namespace including PVCs. Ensure you have backups!
