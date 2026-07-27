"""
Lead enrichers.

Each enricher adds one class of missing data to a lead (public profile,
firmographics, or a deliverable email address). Enrichers are optional: any
provider without credentials is skipped, and the pipeline runs with whichever
ones happen to be configured.
"""

import os
from typing import Any

import httpx

from src.leads import Lead, LeadEnricher, is_valid_email, normalize_domain

GITHUB_API_BASE = "https://api.github.com"
CLEARBIT_COMPANY_BASE = "https://company.clearbit.com/v2"
HUNTER_API_BASE = "https://api.hunter.io/v2"
DEFAULT_TIMEOUT = 15.0

# Hunter returns a 0-100 confidence per address; below this the address is
# more likely to bounce than to reach a buyer, so it is discarded.
MIN_EMAIL_CONFIDENCE = 70


class _HttpEnricher(LeadEnricher):
    """Shared httpx plumbing for HTTP-backed enrichers."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.transport = transport

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET JSON, returning ``{}`` on any HTTP error."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport
            ) as client:
                resp = await client.get(url, headers=headers or {}, params=params or {})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("%s lookup failed: %s", self.id, exc)
            return {}
        return data if isinstance(data, dict) else {}


class GitHubProfileEnricher(_HttpEnricher):
    """Pull public name, company, blog and email from a GitHub profile."""

    id = "github_profile"

    def __init__(
        self,
        token: str = "",
        *,
        base_url: str = GITHUB_API_BASE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def can_enrich(self, lead: Lead) -> bool:
        return bool(lead.metadata.get("github_login"))

    async def lookup(self, lead: Lead) -> dict[str, Any]:
        login = lead.metadata.get("github_login", "")
        data = await self._get_json(
            f"{self.base_url}/users/{login}",
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
            },
        )
        if not data:
            return {}

        signals = []
        followers = data.get("followers")
        if isinstance(followers, int) and followers:
            signals.append(f"followers:{followers}")

        return {
            "name": data.get("name") or "",
            "email": data.get("email") or "",
            "company": (data.get("company") or "").lstrip("@"),
            "domain": normalize_domain(data.get("blog") or ""),
            "location": data.get("location") or "",
            "title": data.get("bio") or "",
            "signals": signals,
        }


class ClearbitEnricher(_HttpEnricher):
    """Add firmographics (legal name, headcount, industry) from a domain."""

    id = "clearbit"

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = CLEARBIT_COMPANY_BASE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("CLEARBIT_API_KEY", "")
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def can_enrich(self, lead: Lead) -> bool:
        return bool(lead.domain)

    async def lookup(self, lead: Lead) -> dict[str, Any]:
        data = await self._get_json(
            f"{self.base_url}/companies/find",
            headers={"Authorization": "Bearer " + self.api_key},
            params={"domain": lead.domain},
        )
        if not data:
            return {}

        metrics = data.get("metrics") or {}
        category = data.get("category") or {}
        signals = []
        for key in ("industry", "sector"):
            value = category.get(key)
            if value:
                signals.append(f"{key}:{value}")
        raised = metrics.get("raised")
        if isinstance(raised, int) and raised:
            signals.append(f"raised:{raised}")

        employees = metrics.get("employees")
        return {
            "company": data.get("legalName") or data.get("name") or "",
            "domain": normalize_domain(data.get("domain") or ""),
            "location": data.get("location") or "",
            "company_size": employees if isinstance(employees, int) else 0,
            "signals": signals,
        }


class HunterEnricher(_HttpEnricher):
    """
    Find a deliverable business email for a company domain.

    Without an email address a lead can never be invoiced, so this enricher is
    what turns a discovered company into a billable customer.
    """

    id = "hunter"

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = HUNTER_API_BASE,
        min_confidence: int = MIN_EMAIL_CONFIDENCE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.min_confidence = min_confidence

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def can_enrich(self, lead: Lead) -> bool:
        # Only worth calling when we have a domain but still no contact.
        return bool(lead.domain) and not is_valid_email(lead.email)

    async def lookup(self, lead: Lead) -> dict[str, Any]:
        payload = await self._get_json(
            f"{self.base_url}/domain-search",
            params={"domain": lead.domain, "api_key": self.api_key, "limit": 10},
        )
        data = payload.get("data") or {}
        best = self._best_contact(data.get("emails") or [])
        if best is None:
            return {}

        name = " ".join(
            part for part in (best.get("first_name"), best.get("last_name")) if part
        )
        return {
            "email": best.get("value") or "",
            "name": name,
            "title": best.get("position") or "",
            "company": data.get("organization") or "",
            "signals": [f"email_confidence:{best.get('confidence', 0)}"],
        }

    def _best_contact(self, emails: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Pick the highest-confidence address, preferring named contacts."""
        candidates = [
            email
            for email in emails
            if is_valid_email(str(email.get("value") or ""))
            and int(email.get("confidence") or 0) >= self.min_confidence
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda e: (
                int(e.get("confidence") or 0),
                bool(e.get("first_name")),
            ),
        )


__all__ = ["ClearbitEnricher", "GitHubProfileEnricher", "HunterEnricher"]
