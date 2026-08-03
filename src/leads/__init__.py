"""
Lead generation and enrichment primitives.

Customer acquisition is modelled as a three-stage pipeline:

``discover`` (a :class:`LeadSource` finds candidate accounts)
→ ``enrich`` (each :class:`LeadEnricher` adds contact and firmographic data)
→ ``score`` (the enriched profile is graded against the ICP so only
qualified leads are handed to billing).

Like revenue streams, every source and enricher degrades to a silent no-op
when its credentials are missing, so the pipeline keeps running with whatever
providers happen to be configured.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

# Free/personal mailbox domains never represent a billable company account.
FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "mail.com",
        "gmx.com",
        "yandex.com",
    }
)

# Score contributions, summed then clamped to 0..100 by :meth:`Lead.score`.
SCORE_WEIGHTS = {
    "email": 30,
    "business_email": 10,
    "company": 15,
    "domain": 10,
    "title": 10,
    "icp_keyword": 15,
    "size": 10,
}

# A lead must reach this score before the platform spends money/effort on it.
DEFAULT_QUALIFY_SCORE = 55

# Company headcount at or above this is treated as a strong buying signal.
STRONG_COMPANY_SIZE = 10


def normalize_domain(value: str) -> str:
    """Reduce a URL, email or hostname to a bare lowercase domain."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "@" in text:
        text = text.rsplit("@", 1)[-1]
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/", 1)[0].split("?", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text.strip(".")


def is_valid_email(value: str) -> bool:
    """Whether ``value`` looks like a deliverable single address."""
    return bool(EMAIL_RE.match((value or "").strip()))


def is_business_email(value: str) -> bool:
    """Whether ``value`` is an email on a company-owned domain."""
    if not is_valid_email(value):
        return False
    return normalize_domain(value) not in FREE_EMAIL_DOMAINS


@dataclass
class Lead:
    """A single prospective customer, progressively enriched in place."""

    lead_id: str
    source: str
    name: str = ""
    email: str = ""
    company: str = ""
    domain: str = ""
    title: str = ""
    location: str = ""
    company_size: int = 0
    profile_url: str = ""
    signals: list[str] = field(default_factory=list)
    enriched_by: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        self.email = (self.email or "").strip().lower()
        self.domain = normalize_domain(self.domain or self.email)

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------

    def merge(self, provider: str, data: dict[str, Any]) -> bool:
        """
        Fill in blank fields from ``data``, never overwriting known values.

        Returns ``True`` when at least one field was populated, so callers can
        report how many leads a provider actually improved.
        """
        changed = False
        for key in ("name", "email", "company", "domain", "title", "location", "profile_url"):
            value = str(data.get(key) or "").strip()
            if not value or getattr(self, key):
                continue
            if key == "email":
                value = value.lower()
                if not is_valid_email(value):
                    continue
            if key == "domain":
                value = normalize_domain(value)
                if not value:
                    continue
            setattr(self, key, value)
            changed = True

        size = data.get("company_size")
        if not self.company_size and isinstance(size, int) and size > 0:
            self.company_size = size
            changed = True

        for signal in data.get("signals") or []:
            if signal not in self.signals:
                self.signals.append(str(signal))
                changed = True

        if not self.domain and self.email:
            self.domain = normalize_domain(self.email)

        if changed and provider and provider not in self.enriched_by:
            self.enriched_by.append(provider)
        return changed

    # ------------------------------------------------------------------
    # Qualification
    # ------------------------------------------------------------------

    def score(self, icp_keywords: tuple[str, ...] = ()) -> int:
        """Grade the lead 0-100 on contactability and ICP fit."""
        total = 0
        if is_valid_email(self.email):
            total += SCORE_WEIGHTS["email"]
            if is_business_email(self.email):
                total += SCORE_WEIGHTS["business_email"]
        if self.company:
            total += SCORE_WEIGHTS["company"]
        if self.domain:
            total += SCORE_WEIGHTS["domain"]
        if self.title:
            total += SCORE_WEIGHTS["title"]
        if self.company_size >= STRONG_COMPANY_SIZE:
            total += SCORE_WEIGHTS["size"]
        if icp_keywords and self._matches_icp(icp_keywords):
            total += SCORE_WEIGHTS["icp_keyword"]
        return max(0, min(100, total))

    def _matches_icp(self, icp_keywords: tuple[str, ...]) -> bool:
        haystack = " ".join(
            [self.company, self.title, self.profile_url, " ".join(self.signals)]
        ).lower()
        return any(word.lower() in haystack for word in icp_keywords if word)

    def is_contactable(self) -> bool:
        """A lead can only be billed if there is somewhere to send the invoice."""
        return is_valid_email(self.email)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "source": self.source,
            "name": self.name,
            "email": self.email,
            "company": self.company,
            "domain": self.domain,
            "title": self.title,
            "location": self.location,
            "company_size": self.company_size,
            "profile_url": self.profile_url,
            "signals": list(self.signals),
            "enriched_by": list(self.enriched_by),
            "discovered_at": self.discovered_at,
        }


class LeadSource(ABC):
    """Discovers candidate leads from one external system."""

    id: str = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"butler.leads.source.{self.id}")

    @property
    def configured(self) -> bool:
        """Whether the source has the credentials it needs."""
        return True

    @abstractmethod
    async def fetch(self, limit: int) -> list[Lead]:
        """Return up to ``limit`` freshly discovered leads."""

    async def discover(self, limit: int) -> list[Lead]:
        """Fetch leads, never raising and returning ``[]`` when unconfigured."""
        if not self.configured or limit <= 0:
            return []
        try:
            return await self.fetch(limit)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Lead source %s failed: %s", self.id, exc)
            return []


class LeadEnricher(ABC):
    """Adds contact/firmographic data to an already discovered lead."""

    id: str = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"butler.leads.enricher.{self.id}")

    @property
    def configured(self) -> bool:
        """Whether the enricher has the credentials it needs."""
        return True

    def can_enrich(self, lead: Lead) -> bool:
        """Skip leads this provider cannot add anything to."""
        return True

    @abstractmethod
    async def lookup(self, lead: Lead) -> dict[str, Any]:
        """Return a partial profile to merge into ``lead``."""

    async def enrich(self, lead: Lead) -> bool:
        """Enrich in place, never raising. Returns whether data was added."""
        if not self.configured or not self.can_enrich(lead):
            return False
        try:
            data = await self.lookup(lead)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Enricher %s failed for %s: %s", self.id, lead.lead_id, exc)
            return False
        if not data:
            return False
        return lead.merge(self.id, data)


class LeadPipeline:
    """
    Runs sources and enrichers, deduplicating leads across cycles.

    The pipeline is intentionally stateful: seen lead ids persist for the
    process lifetime so the platform never rediscovers, re-enriches or
    re-bills the same prospect on the next cycle.
    """

    def __init__(
        self,
        sources: list[LeadSource] | None = None,
        enrichers: list[LeadEnricher] | None = None,
        *,
        icp_keywords: tuple[str, ...] = (),
        qualify_score: int = DEFAULT_QUALIFY_SCORE,
        max_seen: int = 10_000,
    ) -> None:
        self.sources = sources or []
        self.enrichers = enrichers or []
        self.icp_keywords = icp_keywords
        self.qualify_score = qualify_score
        self.max_seen = max_seen
        self._seen: dict[str, None] = {}
        self.discovered_count = 0
        self.enriched_count = 0
        self.qualified_count = 0

    @property
    def configured(self) -> bool:
        """The pipeline can only work with at least one usable source."""
        return any(source.configured for source in self.sources)

    def already_seen(self, lead_id: str) -> bool:
        return lead_id in self._seen

    def _remember(self, lead_id: str) -> None:
        self._seen[lead_id] = None
        # Bounded FIFO so a long-lived process cannot grow without limit.
        while len(self._seen) > self.max_seen:
            self._seen.pop(next(iter(self._seen)))

    async def discover(self, limit_per_source: int) -> list[Lead]:
        """Collect new, previously unseen leads from every source."""
        leads: list[Lead] = []
        for source in self.sources:
            for lead in await source.discover(limit_per_source):
                if self.already_seen(lead.lead_id):
                    continue
                self._remember(lead.lead_id)
                leads.append(lead)
        self.discovered_count += len(leads)
        return leads

    async def enrich(self, leads: list[Lead]) -> int:
        """Run every enricher over every lead. Returns leads improved."""
        improved = 0
        for lead in leads:
            changed = False
            for enricher in self.enrichers:
                if await enricher.enrich(lead):
                    changed = True
            if changed:
                improved += 1
        self.enriched_count += improved
        return improved

    def qualify(self, leads: list[Lead]) -> list[tuple[Lead, int]]:
        """Return ``(lead, score)`` for contactable leads that clear the bar."""
        scored = [
            (lead, lead.score(self.icp_keywords))
            for lead in leads
            if lead.is_contactable()
        ]
        qualified = [item for item in scored if item[1] >= self.qualify_score]
        qualified.sort(key=lambda item: item[1], reverse=True)
        self.qualified_count += len(qualified)
        return qualified

    async def run(self, limit_per_source: int) -> tuple[list[Lead], list[tuple[Lead, int]]]:
        """Execute discover → enrich → qualify for one cycle."""
        leads = await self.discover(limit_per_source)
        if not leads:
            return [], []
        await self.enrich(leads)
        return leads, self.qualify(leads)

    def status(self) -> dict[str, Any]:
        return {
            "sources": [{"id": s.id, "configured": s.configured} for s in self.sources],
            "enrichers": [{"id": e.id, "configured": e.configured} for e in self.enrichers],
            "discovered_total": self.discovered_count,
            "enriched_total": self.enriched_count,
            "qualified_total": self.qualified_count,
        }


__all__ = [
    "DEFAULT_QUALIFY_SCORE",
    "FREE_EMAIL_DOMAINS",
    "Lead",
    "LeadEnricher",
    "LeadPipeline",
    "LeadSource",
    "is_business_email",
    "is_valid_email",
    "normalize_domain",
]
