"""
Multi-tenant provisioning backed by Supabase.

Creates and manages tenant rows in the Supabase ``tenants`` table and writes
audit events to ``tenant_events``.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TenantProvisioner:
    """Manages tenant lifecycle in Supabase."""

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ) -> None:
        self._url = (supabase_url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self._key = supabase_key or os.getenv("SUPABASE_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provision(
        self,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        tier: str,
    ) -> dict[str, Any]:
        """
        Create a new tenant row in Supabase.

        Returns the created tenant record.
        """
        tenant_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row: dict[str, Any] = {
            "tenant_id": tenant_id,
            "tier": tier,
            "status": "active",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "created_at": now,
        }
        self._insert("tenants", row)
        self.record_event(
            stripe_customer_id=stripe_customer_id,
            event_type="tenant.provisioned",
            payload={"tenant_id": tenant_id, "tier": tier},
        )
        logger.info("Provisioned tenant %s (tier=%s)", tenant_id, tier)
        return row

    def deprovision(
        self,
        stripe_customer_id: str,
        stripe_subscription_id: str,
    ) -> None:
        """Mark the tenant as cancelled in Supabase."""
        self._patch(
            "tenants",
            filters={"stripe_customer_id": f"eq.{stripe_customer_id}"},
            data={"status": "cancelled"},
        )
        self.record_event(
            stripe_customer_id=stripe_customer_id,
            event_type="tenant.deprovisioned",
            payload={"stripe_subscription_id": stripe_subscription_id},
        )
        logger.info("Deprovisioned tenant for customer %s", stripe_customer_id)

    def get_by_customer(self, stripe_customer_id: str) -> dict[str, Any] | None:
        """Return the tenant row for a Stripe customer, or None."""
        rows = self._select(
            "tenants",
            filters={"stripe_customer_id": f"eq.{stripe_customer_id}"},
        )
        return rows[0] if rows else None

    def record_event(
        self,
        stripe_customer_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a row to the ``tenant_events`` audit table."""
        import json as _json

        row: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "stripe_customer_id": stripe_customer_id,
            "event_type": event_type,
            "payload": _json.dumps(payload or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._insert("tenant_events", row)

    # ------------------------------------------------------------------
    # Supabase REST helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._key,
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _insert(self, table: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._url or not self._key:
            logger.warning("Supabase not configured; skipping insert into %s", table)
            return []
        url = f"{self._url}/rest/v1/{table}"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=row, headers=self._headers())
            resp.raise_for_status()
            return resp.json() if resp.content else []

    def _patch(
        self,
        table: str,
        filters: dict[str, str],
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self._url or not self._key:
            logger.warning("Supabase not configured; skipping patch on %s", table)
            return []
        params = "&".join(f"{k}={v}" for k, v in filters.items())
        url = f"{self._url}/rest/v1/{table}?{params}"
        with httpx.Client(timeout=10) as client:
            resp = client.patch(url, json=data, headers=self._headers())
            resp.raise_for_status()
            return resp.json() if resp.content else []

    def _select(
        self,
        table: str,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._url or not self._key:
            return []
        params = "&".join(f"{k}={v}" for k, v in (filters or {}).items())
        url = f"{self._url}/rest/v1/{table}?select=*&{params}"
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
