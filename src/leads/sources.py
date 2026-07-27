"""
Lead sources.

Each source turns an external system into :class:`~src.leads.Lead` objects.
Sources are read-only and return ``[]`` when their credentials are missing.
"""

import os
from typing import Any

import httpx

from src.leads import Lead, LeadSource, normalize_domain

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 15.0

# GitHub caps search results at 100 per page.
MAX_SEARCH_PER_PAGE = 100

# Repositories with at least this many stars indicate a funded/serious team.
DEFAULT_MIN_STARS = 25


class GitHubLeadSource(LeadSource):
    """
    Find companies from GitHub repositories matching the ICP.

    Searches for recently pushed repositories whose topics/description match
    the configured ICP keywords, then treats each repository owner as a lead.
    Owner profiles carry a public email, blog and company often enough to make
    this a high-signal, zero-cost top of funnel.
    """

    id = "github"

    def __init__(
        self,
        token: str = "",
        *,
        keywords: tuple[str, ...] = (),
        min_stars: int = DEFAULT_MIN_STARS,
        base_url: str = GITHUB_API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__()
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.keywords = tuple(k for k in keywords if k)
        self.min_stars = min_stars
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    @property
    def configured(self) -> bool:
        # A token is required: unauthenticated search is rate limited to a
        # level that makes continuous prospecting impossible.
        return bool(self.token) and bool(self.keywords)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
        }

    def _query(self) -> str:
        topics = " OR ".join(self.keywords)
        return f"{topics} stars:>={self.min_stars} pushed:>2020-01-01"

    async def fetch(self, limit: int) -> list[Lead]:
        params = {
            "q": self._query(),
            "sort": "updated",
            "order": "desc",
            "per_page": min(limit, MAX_SEARCH_PER_PAGE),
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            resp = await client.get(
                f"{self.base_url}/search/repositories",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()

        leads: list[Lead] = []
        seen_owners: set[str] = set()
        for repo in payload.get("items", [])[:limit]:
            lead = self._to_lead(repo)
            if lead is None or lead.lead_id in seen_owners:
                continue
            seen_owners.add(lead.lead_id)
            leads.append(lead)
        return leads

    def _to_lead(self, repo: dict[str, Any]) -> Lead | None:
        owner = repo.get("owner") or {}
        login = owner.get("login")
        if not login:
            return None

        signals = [f"repo:{repo.get('full_name', '')}"]
        for topic in (repo.get("topics") or [])[:5]:
            signals.append(f"topic:{topic}")
        stars = repo.get("stargazers_count")
        if isinstance(stars, int):
            signals.append(f"stars:{stars}")

        homepage = repo.get("homepage") or ""
        return Lead(
            lead_id=f"github:{login}",
            source=self.id,
            name=login,
            company=login if owner.get("type") == "Organization" else "",
            domain=normalize_domain(homepage),
            profile_url=owner.get("html_url", ""),
            signals=signals,
            metadata={
                "github_login": login,
                "github_api_url": owner.get("url", ""),
                "owner_type": owner.get("type", ""),
                "description": repo.get("description") or "",
            },
        )


__all__ = ["GitHubLeadSource"]
