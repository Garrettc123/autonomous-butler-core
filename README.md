# 🤖 Autonomous Butler Core

**Enterprise-grade autonomous AI orchestration platform** that manages your entire infrastructure, deployments, revenue operations, and customer support with zero human intervention.

## 🎯 What It Does

This system runs **24/7 without human intervention**, handling:

- ✅ **Zero-touch deployments** - Code commits automatically flow to production
- ✅ **Self-healing infrastructure** - Auto-restart failed pods, prevent issues before they occur
- ✅ **Revenue operations** - Retry failed payments, predict churn, offer retention discounts
- ✅ **Customer support** - Answer 85%+ of questions automatically using RAG over docs
- ✅ **Security operations** - Scan for vulnerabilities, auto-patch critical CVEs
- ✅ **Project management** - Auto-create Linear tickets from GitHub issues

## 🏗️ Architecture

```
Event Sources → Event Mesh (Kafka) → Butler Orchestrator → Specialized Agents → Actions
    ↓                                        ↓                      ↓
GitHub PRs                            Route & Coordinate        Deploy, Scale
Stripe Webhooks                       Task Assignment           Fix Issues
K8s Events                            Decision Making           Answer Support
System Metrics                        Learning & Optimization   Manage Revenue
```

### 6 Specialized Agents

1. **DevOps Agent** - Deployments, rollbacks, scaling, PR reviews
2. **Revenue Agent** - Payment retry, churn prevention, MRR tracking
3. **Security Agent** - Vulnerability scanning, auto-patching
4. **Infrastructure Agent** - Self-healing, auto-scaling, predictive maintenance
5. **PM Agent** - Ticket automation, sprint reports, GitHub↔Linear sync
6. **Support Agent** - RAG-powered Q&A, auto-responses, escalation

## 🚀 Quick Start

### Local Development

```bash
# 1. Clone
git clone https://github.com/Garrettc123/autonomous-butler-core.git
cd autonomous-butler-core

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run
docker-compose up -d

# 4. Verify
curl http://localhost:8000/health
```

### Production Deployment (Kubernetes)

```bash
# 1. Create secrets
cp k8s/secrets.yaml.template k8s/secrets.yaml
# Fill in your API keys

# 2. Deploy
kubectl apply -f k8s/

# 3. Verify
kubectl get pods -n autonomous-butler
kubectl logs -f -n autonomous-butler deployment/butler-core
```

### One-Command Full Deploy

```bash
chmod +x deploy-all.sh
./deploy-all.sh
```

This deploys:
- Kafka (event mesh)
- Redis (caching)
- PostgreSQL (state)
- Prometheus (metrics)
- Grafana (dashboards)
- Butler Core (orchestrator)

## 📡 API Endpoints

### Commands
```bash
# Execute natural language commands
curl -X POST https://butler.your-domain.com/api/butler/command \
  -H "Content-Type: application/json" \
  -d '{"text": "Deploy revenue-agent to production"}'

# Get system status
curl https://butler.your-domain.com/api/butler/status

# View metrics
curl https://butler.your-domain.com/api/butler/metrics
```

### Webhooks
```bash
# GitHub webhook
POST /api/events/github

# Stripe webhook
POST /api/events/stripe

# Kubernetes events
POST /api/events/kubernetes
```

## ⚙️ Configuration

All configuration via environment variables:

```bash
# AI Models
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Integrations
GITHUB_TOKEN=ghp_...
LINEAR_API_KEY=lin_...
STRIPE_SECRET_KEY=sk_live_...

# Infrastructure
KUBERNETES_CLUSTER=production
KAFKA_BROKERS=kafka:9092
PROMETHEUS_URL=http://prometheus:9090

# Alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
PAGERDUTY_API_KEY=...
```

## 📊 Monitoring

### Grafana Dashboards

Access at `http://localhost:3000` (admin/admin):

- **System Overview** - Autonomous actions, deployments, self-healing
- **Agent Status** - Individual agent performance
- **Revenue Metrics** - MRR, payments recovered, churn prevented
- **Infrastructure Health** - Pod status, resource usage

### Prometheus Metrics

Key metrics exposed at `/metrics`:

- `butler_deployments_total` - Successful deployments
- `butler_rollbacks_total` - Auto-rollbacks triggered
- `butler_pods_restarted_total` - Self-healing actions
- `butler_payments_recovered_total` - Revenue recovered
- `butler_questions_answered_total` - Support auto-responses

## 🔒 Security

- **Zero-trust architecture** - All inter-service communication encrypted
- **Auto-patching** - Critical CVEs patched within 24 hours
- **Vulnerability scanning** - Daily Trivy scans on all images
- **Secret management** - Kubernetes secrets, never committed to Git
- **Audit logging** - All autonomous actions logged to immutable store

## 📈 Scalability

- **Horizontal scaling** - Auto-scale from 3 to 10 replicas based on load
- **Event-driven** - Handle millions of events per day via Kafka
- **Async processing** - Non-blocking operations for high throughput
- **Database optimization** - Connection pooling, read replicas

## 🧪 Testing

```bash
# Run tests
pytest tests/ -v --cov=src

# Integration tests
pytest tests/test_integration.py

# Load testing
locust -f tests/load_test.py --host=http://localhost:8000
```

## 📚 Documentation

- [Architecture Guide](docs/architecture.md)
- [API Reference](docs/api.md)
- [Deployment Guide](docs/deployment.md)
- [Agent Development](docs/agents.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🤝 Contributing

This is an open-source project. Contributions welcome!

1. Fork the repo
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📜 License

MIT License - Free for commercial use

## 🌟 Star History

If this project helps you, please ⭐ star it on GitHub!

## 🔗 Related Projects

- [autonomous-event-mesh](https://github.com/Garrettc123/autonomous-event-mesh) - Event streaming layer
- [autonomous-self-healing](https://github.com/Garrettc123/autonomous-self-healing) - Infrastructure agent
- [autonomous-zero-touch-deploy](https://github.com/Garrettc123/autonomous-zero-touch-deploy) - CI/CD pipeline
- [autonomous-revenue-ops](https://github.com/Garrettc123/autonomous-revenue-ops) - Revenue agent
- [autonomous-support-ai](https://github.com/Garrettc123/autonomous-support-ai) - Support agent

---

**Built with ❤️ by [Garrett Carrol](https://github.com/Garrettc123) | [Garcar Enterprise](https://github.com/Garrettc123)**

**Status:** ✅ Production-ready | 🚀 Deployed at scale | 🤖 Fully autonomous