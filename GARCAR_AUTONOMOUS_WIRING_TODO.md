# Garcar Autonomous Wiring TODO for autonomous-butler-core

Role: `ai_orchestration`

_Live fan-out: 2026-09-12 (wet / CASH_LOCK)_

## Required Garcar Base Contract
- Implement `/health`, `/meta`, `/metrics`, `/events` endpoints.

## Event Bus Wiring
- Emit required events for this role.
- Consume required arbitrage/control-plane events.

## Current Full-Stack Components
- backend_api: None
- frontend_ui: None
- payment_hook: None
- event_bus_connected: False
- observability_connected: False

## Wiring Tasks
1. Add or verify Garcar Base Contract endpoints.
2. Add NATS/Redis Streams client and emit/consume required topics.
3. Ensure metrics/events appear in Zeus/Atlas dashboards.
4. Add tests for contract + event wiring.

## Safety
- Draft PR only. Do not auto-merge.
- Respect CASH_LOCK: no live spend / no silent outbound.
