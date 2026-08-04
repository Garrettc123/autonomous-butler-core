"""
Autonomous outreach agent.

Takes a qualified Lead and sends a personalized first-touch message
using signals already on the lead object (repo, topics, stars, company).

Delivery channels (in priority order):
  1. Email  — if the lead has a contactable business email
  2. GitHub  — post a GitHub issue or discussion on their top repo
                when no email is available but a github_login is known

Each lead is contacted at most once. A delivered set persists for the
process lifetime (same pattern as LeadPipeline._seen).
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Any

import httpx

from src.leads import Lead, is_business_email

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# ---------------------------------------------------------------------------
# Message generation
# ---------------------------------------------------------------------------

SENDER_NAME = "Garrett Carroll"
SENDER_COMPANY = "Garcar Enterprise"
SENDER_EMAIL = os.getenv("OUTREACH_FROM_EMAIL", "")
CALENDLY_LINK = os.getenv("OUTREACH_CALENDLY", "https://garcar.io/call")


def _extract_repo(signals: list[str]) -> str:
    """Pull the first repo signal, e.g. 'repo:owner/name' → 'owner/name'."""
    for s in signals:
        if s.startswith("repo:"):
            return s[5:]
    return ""


def _extract_topics(signals: list[str], limit: int = 3) -> list[str]:
    topics = [s[6:] for s in signals if s.startswith("topic:")]
    return topics[:limit]


def _extract_stars(signals: list[str]) -> str:
    for s in signals:
        if s.startswith("stars:"):
            return s[6:]
    return ""


def build_subject(lead: Lead) -> str:
    repo = _extract_repo(lead.signals)
    if repo:
        return f"Quick question about {repo}"
    if lead.company:
        return f"Quick question for {lead.company}"
    return f"Quick question for {lead.name or 'you'}"


def build_body(lead: Lead) -> str:
    repo = _extract_repo(lead.signals)
    topics = _extract_topics(lead.signals)
    stars = _extract_stars(lead.signals)

    # Opening line — specific to what the lead actually built
    if repo and topics:
        topic_str = ", ".join(topics)
        opening = (
            f"I came across {repo} ({stars} stars) while scanning for teams"
            f" working on {topic_str} — looks like genuinely serious work."
        )
    elif repo:
        opening = (
            f"I came across {repo}{f' ({stars} stars)' if stars else ''} "
            f"and it caught my attention — looks like genuinely serious work."
        )
    else:
        opening = f"I came across your work and it caught my attention."

    body = f"""Hi {lead.name or 'there'},

{opening}

I'm {SENDER_NAME}, founder of {SENDER_COMPANY}. We've built a fully autonomous \
AI infrastructure platform — multi-agent orchestration, self-healing CI/CD, \
autonomous lead acquisition, and a shared event bus that connects every system \
into one organism. The whole stack runs 24/7 without human intervention.

Based on what you're building, I thought it might be relevant. \
Would a 15-minute call make sense?

{CALENDLY_LINK}

Either way — keep shipping.

{SENDER_NAME}
{SENDER_COMPANY}
"""
    return body


# ---------------------------------------------------------------------------
# Delivery channels
# ---------------------------------------------------------------------------


@dataclass
class OutreachResult:
    lead_id: str
    channel: str
    success: bool
    detail: str = ""


class EmailChannel:
    """
    Send via SMTP. Reads credentials from environment:
      OUTREACH_SMTP_HOST, OUTREACH_SMTP_PORT (default 465)
      OUTREACH_SMTP_USER, OUTREACH_SMTP_PASS
      OUTREACH_FROM_EMAIL
    """

    id = "email"

    def __init__(self) -> None:
        self.host = os.getenv("OUTREACH_SMTP_HOST", "")
        self.port = int(os.getenv("OUTREACH_SMTP_PORT", "465"))
        self.user = os.getenv("OUTREACH_SMTP_USER", "")
        self.password = os.getenv("OUTREACH_SMTP_PASS", "")
        self.from_email = os.getenv("OUTREACH_FROM_EMAIL", "")

    @property
    def configured(self) -> bool:
        return all([self.host, self.user, self.password, self.from_email])

    def send(self, lead: Lead) -> OutreachResult:
        if not self.configured:
            return OutreachResult(lead.lead_id, self.id, False, "smtp not configured")
        if not is_business_email(lead.email):
            return OutreachResult(lead.lead_id, self.id, False, "no business email")

        msg = MIMEText(build_body(lead), "plain")
        msg["Subject"] = build_subject(lead)
        msg["From"] = f"{SENDER_NAME} <{self.from_email}>"
        msg["To"] = lead.email

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx) as server:
                server.login(self.user, self.password)
                server.sendmail(self.from_email, [lead.email], msg.as_string())
            logger.info("Email sent to %s <%s>", lead.lead_id, lead.email)
            return OutreachResult(lead.lead_id, self.id, True, lead.email)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email failed for %s: %s", lead.lead_id, exc)
            return OutreachResult(lead.lead_id, self.id, False, str(exc))


class GitHubIssueChannel:
    """
    Fallback: open a GitHub issue on the lead's top repo as an intro.
    Only fires when email is unavailable and github_login is known.
    """

    id = "github_issue"

    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN", "")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def send(self, lead: Lead) -> OutreachResult:
        if not self.configured:
            return OutreachResult(lead.lead_id, self.id, False, "no github token")

        repo = _extract_repo(lead.signals)
        if not repo:
            return OutreachResult(lead.lead_id, self.id, False, "no repo signal")

        payload = {
            "title": build_subject(lead),
            "body": build_body(lead),
            "labels": [],
        }

        try:
            resp = httpx.post(
                f"{GITHUB_API_BASE}/repos/{repo}/issues",
                headers=self._headers(),
                json=payload,
                timeout=15.0,
            )
            resp.raise_for_status()
            issue_url = resp.json().get("html_url", "")
            logger.info("GitHub issue opened for %s: %s", lead.lead_id, issue_url)
            return OutreachResult(lead.lead_id, self.id, True, issue_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub issue failed for %s: %s", lead.lead_id, exc)
            return OutreachResult(lead.lead_id, self.id, False, str(exc))


# ---------------------------------------------------------------------------
# Outreach agent
# ---------------------------------------------------------------------------


@dataclass
class OutreachAgent:
    """
    Sends first-touch messages to qualified leads.

    Channels are tried in order; the first success stops the chain.
    Delivered leads are remembered so they are never contacted twice.
    """

    channels: list[Any] = field(
        default_factory=lambda: [EmailChannel(), GitHubIssueChannel()]
    )
    _delivered: dict[str, None] = field(default_factory=dict, repr=False)
    sent_count: int = field(default=0, repr=False)
    failed_count: int = field(default=0, repr=False)

    def already_contacted(self, lead_id: str) -> bool:
        return lead_id in self._delivered

    def contact(self, lead: Lead) -> OutreachResult | None:
        """Send to lead via the first working channel. Returns None if skipped."""
        if self.already_contacted(lead.lead_id):
            logger.debug("Skipping %s — already contacted.", lead.lead_id)
            return None

        for channel in self.channels:
            result = channel.send(lead)
            if result.success:
                self._delivered[lead.lead_id] = None
                self.sent_count += 1
                return result

        self.failed_count += 1
        logger.warning("All channels failed for %s", lead.lead_id)
        return OutreachResult(lead.lead_id, "none", False, "all channels exhausted")

    def contact_all(self, qualified: list[tuple[Lead, int]]) -> list[OutreachResult]:
        """Send to every lead in the qualified list. Returns all results."""
        results = []
        for lead, score in qualified:
            logger.info("Contacting %s (score=%d)", lead.lead_id, score)
            result = self.contact(lead)
            if result:
                results.append(result)
        return results

    def status(self) -> dict[str, Any]:
        return {
            "sent_total": self.sent_count,
            "failed_total": self.failed_count,
            "delivered_count": len(self._delivered),
            "channels": [{"id": c.id, "configured": c.configured} for c in self.channels],
        }


__all__ = [
    "OutreachAgent",
    "OutreachResult",
    "EmailChannel",
    "GitHubIssueChannel",
    "build_body",
    "build_subject",
]
