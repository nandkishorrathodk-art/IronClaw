# Ironclaw Monitoring & Observability Guide

Complete guide to monitoring Ironclaw in production.

## Monitoring Stack

Ironclaw includes a comprehensive monitoring stack:

- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **Jaeger**: Distributed tracing
- **Sentry**: Error tracking (optional)

## Quick Start

### Access Monitoring UIs

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
# Default credentials: admin / admin (change on first login)

# Kubernetes
kubectl port-forward -n ironclaw svc/grafana 3000:3000
```

**Jaeger**:
```bash
# Docker/Kubernetes
http://localhost:16686
```

## Key Metrics

### 1. HTTP Metrics

```promql
# Request rate
rate(ironclaw_http_requests_total[5m])

# Error rate
rate(ironclaw_http_requests_total{status_code=~"5.."}[5m])

# P95 latency
histogram_quantile(0.95, rate(ironclaw_http_request_duration_seconds_bucket[5m]))

# P99 latency
histogram_quantile(0.99, rate(ironclaw_http_request_duration_seconds_bucket[5m]))
```

### 2. AI Provider Metrics

```promql
# AI request rate by provider
rate(ironclaw_ai_requests_total[5m])

# AI cost tracking
ironclaw_ai_cost_usd_total

# AI error rate
rate(ironclaw_ai_errors_total[5m])

# Token usage
rate(ironclaw_ai_tokens_total[5m])
```

### 3. System Metrics

```promql
# Memory usage
ironclaw_system_memory_bytes{type="used"}

# CPU usage
ironclaw_system_cpu_percent

# Active database connections
ironclaw_db_connections_active
```

### 4. Plugin Metrics

```promql
# Plugin execution rate
rate(ironclaw_plugin_executions_total[5m])

# Plugin execution duration
histogram_quantile(0.95, rate(ironclaw_plugin_execution_duration_seconds_bucket[5m]))
```

## Grafana Dashboards

### Pre-configured Dashboards

1. **Ironclaw System Overview** (`ironclaw-overview.json`)
   - HTTP request metrics
   - System resources
   - AI provider usage
   - Cost tracking

2. **Performance Dashboard**
   - Request latency
   - Throughput
   - Error rates

3. **AI Usage Dashboard**
   - Provider distribution
   - Token usage
   - Cost analysis

### Importing Dashboards

```bash
# Copy dashboards to Grafana
docker cp config/grafana/dashboards/ironclaw-overview.json ironclaw-grafana:/etc/grafana/provisioning/dashboards/
```

## Alerts

### Configure Prometheus Alerts

Create `config/prometheus/alerts/ironclaw.yml`:

```yaml
groups:
  - name: ironclaw
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: rate(ironclaw_http_requests_total{status_code=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High HTTP error rate"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"
      
      # High latency
      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(ironclaw_http_request_duration_seconds_bucket[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "P99 latency is {{ $value }}s (threshold: 100ms)"
      
      # Memory pressure
      - alert: HighMemoryUsage
        expr: ironclaw_system_memory_bytes{type="used"} / ironclaw_system_memory_bytes{type="total"} > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanizePercentage }}"
      
      # AI cost threshold
      - alert: HighAICost
        expr: increase(ironclaw_ai_cost_usd_total[1h]) > 10
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "High AI API cost"
          description: "AI cost increased by ${{ $value }} in the last hour"
```

### Alert Routing (Alertmanager)

Configure Alertmanager to send alerts:

```yaml
# config/alertmanager/config.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'slack'

receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

## Distributed Tracing (Jaeger)

### View Traces

1. Open Jaeger UI: http://localhost:16686
2. Select service: `ironclaw-api`
3. Search for traces by:
   - Time range
   - Operation (endpoint)
   - Tags (user_id, status_code, etc.)

### Example Queries

- Find slow requests: Filter by duration > 1s
- Find errors: Filter by tag `error=true`
- Trace specific request: Search by trace ID

## Log Aggregation

### Using Loguru

Ironclaw uses structured logging with Loguru:

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("Request processed", extra={"user_id": 123, "duration": 0.5})
```

### Log Format

**Development** (human-readable):
```
2024-02-22 15:30:45.123 | INFO     | src.api.main:root:42 - Request processed
```

**Production** (JSON):
```json
{
  "timestamp": "2024-02-22T15:30:45.123Z",
  "level": "INFO",
  "logger": "src.api.main",
  "message": "Request processed",
  "user_id": 123,
  "duration": 0.5
}
```

### Centralized Logging (Optional)

**Using Loki**:
```bash
docker run -d --name=loki -p 3100:3100 grafana/loki:latest
```

**Using ELK Stack**:
- Elasticsearch for storage
- Logstash for processing
- Kibana for visualization

## Error Tracking (Sentry)

### Setup

```env
ENABLE_SENTRY=true
SENTRY_DSN=https://xxxxx@sentry.io/xxxxx
```

### Features

- Automatic error reporting
- Stack traces with context
- Release tracking
- Performance monitoring
- User feedback

### Sentry Dashboard

View errors at: https://sentry.io/organizations/your-org/issues/

## Performance Monitoring

### Key Performance Indicators (KPIs)

| Metric | Target | Critical |
|--------|--------|----------|
| **P50 Latency** | < 50ms | > 100ms |
| **P99 Latency** | < 100ms | > 500ms |
| **Error Rate** | < 0.1% | > 1% |
| **Availability** | > 99.9% | < 99% |
| **Memory Usage** | < 80% | > 90% |

### Monitoring Checklist

Daily:
- [ ] Check error rate
- [ ] Review slow queries
- [ ] Verify backup completion

Weekly:
- [ ] Review cost metrics
- [ ] Analyze performance trends
- [ ] Update dashboards

Monthly:
- [ ] Capacity planning
- [ ] Security audit
- [ ] Performance optimization

## Troubleshooting

### High Memory Usage

```promql
# Find memory-intensive endpoints
topk(5, sum by (endpoint) (ironclaw_http_requests_in_progress))
```

### Slow Requests

```promql
# Find slowest endpoints
topk(5, histogram_quantile(0.99, rate(ironclaw_http_request_duration_seconds_bucket[5m])))
```

### Database Issues

```promql
# Check database connection pool
ironclaw_db_connections_active / 10 > 0.8  # 80% of pool size
```

## Best Practices

1. **Set up alerts** for critical metrics
2. **Review dashboards** daily
3. **Investigate anomalies** immediately
4. **Keep retention policies** (30 days for metrics, 7 days for logs)
5. **Use distributed tracing** to debug complex issues
6. **Monitor costs** to avoid surprises
7. **Document incidents** for future reference

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Sentry Documentation](https://docs.sentry.io/)
