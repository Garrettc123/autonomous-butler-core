# Garcar Autonomous Wiring TODO for autonomous-butler-core

Role: `ai_orchestration`

_Live fan-out: 2026-09-12 (wet / CASH_LOCK)_

## Required Garcar Base Contract
- [x] `/health` — present (status, system, version, timestamp)
- [x] `/meta` — **added** (contract_version 1.0.0, role ai_orchestration)
- [x] `/metrics` — present (JSON counters)
- [x] `/events` — present (bus-backed ring)

## Event Bus Wiring
- [ ] Emit required events for this role (`garcar.autonomous-butler-core.{event_type}`).
- [ ] Consume required arbitrage/control-plane events.
- Remaining: NATS/Redis Streams client; Zeus/Atlas dashboard visibility; contract+event tests.

## Current Full-Stack Components
- backend_api: FastAPI (`src/main.py`)
- frontend_ui: Jinja dashboard
- payment_hook: Stripe webhook
- event_bus_connected: False (in-process bus only)
- observability_connected: False

## Wiring Tasks
1. ~~Add or verify Garcar Base Contract endpoints.~~ **DONE**
2. Add NATS/Redis Streams client and emit/consume required topics.
3. Ensure metrics/events appear in Zeus/Atlas dashboards.
4. Add tests for contract + event wiring.

## Safety
- Draft PR only. Do not auto-merge.
- Respect CASH_LOCK: no live spend / no silent outbound.
