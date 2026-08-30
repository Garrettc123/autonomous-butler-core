"""
Garcar Enterprise — GitHub Integration
Wires GitHub webhook events into the Butler Core agent dispatch system.
"""
import os
import hmac
import hashlib
import json
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
from event_bus_sdk import ButlerEventBus

app = FastAPI(title="Garcar GitHub Integration")
bus = ButlerEventBus()

GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]

def verify_signature(payload: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    payload = await request.body()
    if not verify_signature(payload, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = json.loads(payload)
    event_type = x_github_event

    # Route to appropriate Butler agents
    if event_type == "push":
        await bus.emit("github.push", {
            "repo": data["repository"]["full_name"],
            "ref": data["ref"],
            "pusher": data["pusher"]["name"],
            "commits": len(data.get("commits", []))
        }, agents=["DevOpsAgent"])

    elif event_type == "pull_request":
        await bus.emit("github.pull_request", {
            "action": data["action"],
            "pr_number": data["pull_request"]["number"],
            "repo": data["repository"]["full_name"],
            "title": data["pull_request"]["title"]
        }, agents=["DevOpsAgent", "PMAgent"])

    elif event_type == "workflow_run":
        status = data["workflow_run"]["conclusion"]
        await bus.emit("github.workflow_run", {
            "workflow": data["workflow_run"]["name"],
            "status": status,
            "repo": data["repository"]["full_name"]
        }, agents=["DevOpsAgent"])
        if status == "failure":
            # Auto-create Linear issue on CI failure
            await bus.emit("linear.create_issue", {
                "title": f"CI Failure: {data['workflow_run']['name']}",
                "team": "DevOps",
                "priority": 1,
                "labels": ["ci-failure", "automated"]
            }, agents=["PMAgent"])

    elif event_type == "release":
        await bus.emit("github.release", {
            "tag": data["release"]["tag_name"],
            "repo": data["repository"]["full_name"],
            "name": data["release"]["name"]
        }, agents=["DevOpsAgent", "PMAgent", "SupportAgent"])

    return {"status": "dispatched", "event": event_type}
