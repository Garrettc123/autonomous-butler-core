# Changelog

All notable changes to the Autonomous Butler Core project will be documented in this file.

## [Unreleased]

### Added
- 💰 Pluggable `RevenueStream` abstraction with a per-environment stream registry
- 💳 Five revenue streams: `subscriptions`, `usage_based`, `one_time`, `dunning`, `expansion`
- 🔁 Failed-payment recovery with exponential backoff (1h → 6h → 24h → 72h)
- 📈 Seat-growth upsell detection alongside existing churn alerts
- 🔌 `GET /revenue/streams` and `GET /revenue/streams/{id}` endpoints
- 🪝 `POST /webhooks/stripe` with HMAC signature and replay-window verification
- 📊 Per-stream counters in `/metrics` and a Revenue Streams dashboard section
- ⚙️ `REVENUE_STREAMS`, `STRIPE_WEBHOOK_SECRET` and `STRIPE_USAGE_PRICE_ID` configuration

### Changed
- ♻️ `RevenueAgent` is now a stream orchestrator and holds no Stripe logic
- 🚀 CI/CD pipeline now runs the real test suite, builds/pushes the image, and
  performs a real Kubernetes rollout with automatic rollback on failure

## [2.0.0] - 2026-02-07

### Added
- ✨ Complete autonomous AI orchestration platform
- 🤖 6 specialized agents (DevOps, Revenue, Security, PM, Support, Infra)
- 🚀 Zero-touch deployment pipeline
- 🔧 Self-healing infrastructure
- 💰 Autonomous revenue operations
- 🔒 Security scanning and auto-patching
- 📊 Prometheus + Grafana monitoring
- ⚙️ Production-ready Kubernetes configs
- 🐳 Docker Compose for local development
- 🔄 Complete CI/CD pipeline

### Features
- Event-driven architecture with Kafka
- Real-time metrics and dashboards
- Auto-scaling from 3-10 replicas
- Payment retry and churn prevention
- RAG-powered customer support
- GitHub ↔ Linear synchronization
- Automatic rollbacks on failures
- Vulnerability scanning with Trivy

### Documentation
- Complete README with quick start
- Architecture diagrams
- API documentation
- Deployment guides
- Configuration examples

## [1.0.0] - 2026-01-01

### Initial Release
- Basic orchestrator framework
- Simple agent architecture
- Manual deployment process