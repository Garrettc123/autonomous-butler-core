"""
Garcar Enterprise — Slack Integration
Bi-directional: Butler agents post to Slack; Slack commands trigger agents.
"""
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

class GarcarSlack:
    def __init__(self):
        self.client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        self.channels = {
            "revenue": os.environ.get("SLACK_CHANNEL_REVENUE", "#garcar-revenue"),
            "ops": os.environ.get("SLACK_CHANNEL_OPS", "#garcar-ops"),
            "alerts": os.environ.get("SLACK_CHANNEL_ALERTS", "#garcar-alerts"),
            "ai": os.environ.get("SLACK_CHANNEL_AI", "#garcar-ai")
        }

    def post_revenue_event(self, amount: float, source: str, description: str):
        self.client.chat_postMessage(
            channel=self.channels["revenue"],
            blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "💰 Revenue Event"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Amount:* ${amount:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Source:* {source}"},
                    {"type": "mrkdwn", "text": f"*Details:* {description}"}
                ]}
            ]
        )

    def post_agent_alert(self, agent: str, severity: str, message: str):
        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(severity, "📢")
        self.client.chat_postMessage(
            channel=self.channels["alerts"],
            text=f"{emoji} *[{agent}]* {message}"
        )

    def post_integration_status(self, platform: str, status: str, detail: str):
        color = {"healthy": "good", "degraded": "warning", "down": "danger"}.get(status, "#888")
        self.client.chat_postMessage(
            channel=self.channels["ops"],
            attachments=[{"color": color, "text": f"*{platform}* integration is *{status}*: {detail}"}]
        )

# Register as event bus subscriber
slack = GarcarSlack()

async def handle_revenue_event(event):
    slack.post_revenue_event(event["amount"], event["source"], event["description"])

async def handle_agent_alert(event):
    slack.post_agent_alert(event["agent"], event["severity"], event["message"])

bus.subscribe("revenue.*", handle_revenue_event)
bus.subscribe("agent.alert", handle_agent_alert)
