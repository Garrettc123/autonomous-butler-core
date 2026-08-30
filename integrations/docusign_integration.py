"""
Garcar Enterprise — DocuSign Integration
Autonomous contract and NDA sending via DocuSign eSignature REST API.
Uses JWT Grant (server-to-server) — no user interaction required.
"""
import os
import jwt
import time
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

DOCUSIGN_BASE = os.environ.get("DOCUSIGN_BASE_URL", "https://na4.docusign.net/restapi")
DOCUSIGN_OAUTH = os.environ.get("DOCUSIGN_OAUTH_BASE_URL", "https://account.docusign.com")

class GarcarDocuSign:
    def __init__(self):
        self.account_id = os.environ.get("DOCUSIGN_ACCOUNT_ID", "")
        self.integration_key = os.environ.get("DOCUSIGN_INTEGRATION_KEY", "")
        self.rsa_private_key = os.environ.get("DOCUSIGN_RSA_PRIVATE_KEY", "").replace("\\n", "\n")
        self._access_token = None
        self._token_expiry = 0

    async def get_access_token(self) -> str:
        """JWT Grant — obtain access token autonomously, no user click required."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        claim = {
            "iss": self.integration_key,
            "sub": self.account_id,
            "aud": "account.docusign.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "scope": "signature impersonation"
        }
        assertion = jwt.encode(claim, self.rsa_private_key, algorithm="RS256")
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{DOCUSIGN_OAUTH}/oauth/token",
                              data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                    "assertion": assertion}) as r:
                data = await r.json()
                self._access_token = data["access_token"]
                self._token_expiry = time.time() + data["expires_in"]
                return self._access_token

    async def send_envelope(self, template_id: str, signer_name: str, signer_email: str, subject: str, custom_fields: dict = {}) -> dict:
        """Send a contract envelope from a DocuSign template."""
        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "templateId": template_id,
            "templateRoles": [{"email": signer_email, "name": signer_name, "roleName": "Signer"}],
            "emailSubject": subject,
            "status": "sent"
        }
        url = f"{DOCUSIGN_BASE}/v2.1/accounts/{self.account_id}/envelopes"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=payload) as r:
                data = await r.json()
                envelope_id = data.get("envelopeId", "")
                await bus.emit("docusign.envelope_sent", {
                    "envelope_id": envelope_id, "signer": signer_email,
                    "template": template_id, "subject": subject
                }, agents=["RevenueOpsAgent", "PMAgent"])
                return data

    async def send_contract(self, signer_name: str, signer_email: str, deal_amount: float) -> dict:
        return await self.send_envelope(
            template_id=os.environ.get("DOCUSIGN_CONTRACT_TEMPLATE_ID", ""),
            signer_name=signer_name, signer_email=signer_email,
            subject=f"Garcar Enterprise — Service Agreement (${deal_amount:,.0f})"
        )

docusign = GarcarDocuSign()

async def handle_deal_closed(event):
    """Auto-send contract when HubSpot deal reaches Closed Won."""
    if event.get("stage") == "closed_won":
        await docusign.send_contract(event["contact_name"], event["contact_email"], event["amount"])

bus.subscribe("hubspot.deal_closed_won", handle_deal_closed)
