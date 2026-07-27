"""
Thin async Stripe REST client shared by all revenue streams.

Wraps :mod:`httpx` with the small amount of Stripe-specific behaviour the
streams need: bearer auth, form-encoded POST bodies, bracket-style nested
params, and error handling that returns ``None`` instead of raising so a
transient Stripe outage never crashes an agent cycle.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"
DEFAULT_TIMEOUT = 15.0

# Stripe rejects webhook signatures whose timestamp is outside this window.
WEBHOOK_TOLERANCE_SECONDS = 300


class StripeClient:
    """Minimal async wrapper around the Stripe REST API."""

    def __init__(
        self,
        secret_key: str = "",
        *,
        base_url: str = STRIPE_API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.secret_key = secret_key or os.getenv("STRIPE_SECRET_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Injectable transport, used by tests to stub the Stripe API.
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.secret_key)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.secret_key}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict | None:
        """GET a Stripe resource, returning ``None`` on any HTTP error."""
        if not self.configured:
            return None
        try:
            async with self._client() as client:
                resp = await client.get(
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=self._headers(),
                    params=params or {},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Stripe GET %s failed: %s", path, exc)
            return None

    async def post(self, path: str, data: dict[str, Any] | None = None) -> dict | None:
        """POST form-encoded data to Stripe, returning ``None`` on error."""
        if not self.configured:
            return None
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=self._headers(),
                    data=data or {},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Stripe POST %s failed: %s", path, exc)
            return None


def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
    *,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """
    Verify a Stripe ``Stripe-Signature`` header against the raw request body.

    Implements Stripe's scheme: the signed payload is ``"{timestamp}.{body}"``
    HMAC-SHA256'd with the endpoint secret. Comparison is constant-time and
    old timestamps are rejected to prevent replay attacks.
    """
    if not secret or not signature_header:
        return False

    timestamp: str | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        return False

    try:
        signed_at = int(timestamp)
    except ValueError:
        return False

    current = time.time() if now is None else now
    if abs(current - signed_at) > tolerance:
        logger.warning("Rejected Stripe webhook: timestamp outside tolerance")
        return False

    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
