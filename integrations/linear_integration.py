"""
Garcar Enterprise — Linear Integration
Auto-creates, assigns, and resolves Linear issues from system events.
Supports all Butler agents: DevOps, Revenue, Security, PM, Support.
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

LINEAR_API = "https://api.linear.app/graphql"
LINEAR_HEADERS = {
    "Authorization": os.environ.get("LINEAR_API_KEY", ""),
    "Content-Type": "application/json"
}

PRIORITY_MAP = {1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}

async def create_linear_issue(title: str, description: str, team_id: str, priority: int = 3, labels: list = []) -> str:
    query = """
    mutation CreateIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url }
      }
    }
    """
    variables = {
        "input": {
            "title": title,
            "description": description,
            "teamId": team_id,
            "priority": priority,
            "labelIds": labels
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(LINEAR_API, json={"query": query, "variables": variables}, headers=LINEAR_HEADERS) as resp:
            data = await resp.json()
            issue = data["data"]["issueCreate"]["issue"]
            return issue["url"]

async def handle_linear_issue_request(event):
    """Butler agents emit 'linear.create_issue' events; this handler executes them."""
    team_id = os.environ.get(f"LINEAR_TEAM_{event.get('team', 'DEFAULT').upper()}_ID",
                             os.environ.get("LINEAR_TEAM_ID", ""))
    url = await create_linear_issue(
        title=event["title"],
        description=event.get("description", "Auto-created by Garcar Butler Core"),
        team_id=team_id,
        priority=event.get("priority", 3),
        labels=event.get("label_ids", [])
    )
    await bus.emit("linear.issue_created", {"url": url, "title": event["title"]}, agents=["PMAgent"])

bus.subscribe("linear.create_issue", handle_linear_issue_request)
