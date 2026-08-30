"""
Garcar Enterprise — Google Tasks Integration
Autonomous task creation + completion tracking via Google Tasks API.
Uses service account or refresh token for server-to-server auth.
"""
import os
import aiohttp
from datetime import datetime, timezone, timedelta
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

GOOGLE_TASKS_BASE = "https://tasks.googleapis.com/tasks/v1"
TASKLIST_ID = os.environ.get("GOOGLE_TASKS_TASKLIST_ID", "@default")

class GarcarGoogleTasks:
    def __init__(self):
        self._token = None
        self._token_expiry = 0

    async def _get_token(self) -> str:
        """Refresh OAuth2 access token using stored refresh token."""
        if self._token and datetime.now().timestamp() < self._token_expiry - 60:
            return self._token
        async with aiohttp.ClientSession() as s:
            async with s.post("https://oauth2.googleapis.com/token", data={
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                "refresh_token": os.environ.get("GOOGLE_REFRESH_TOKEN", ""),
                "grant_type": "refresh_token"
            }) as r:
                data = await r.json()
                self._token = data.get("access_token", "")
                self._token_expiry = datetime.now().timestamp() + data.get("expires_in", 3600)
                return self._token

    async def create_task(self, title: str, notes: str = "", due_days: int = 1) -> dict:
        token = await self._get_token()
        due = (datetime.now(timezone.utc) + timedelta(days=due_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload = {"title": title, "notes": notes, "due": due, "status": "needsAction"}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{GOOGLE_TASKS_BASE}/lists/{TASKLIST_ID}/tasks",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload
            ) as r:
                data = await r.json()
                await bus.emit("google_tasks.task_created", {"id": data.get("id"), "title": title}, agents=["PMAgent"])
                return data

    async def complete_task(self, task_id: str) -> dict:
        token = await self._get_token()
        async with aiohttp.ClientSession() as s:
            async with s.patch(
                f"{GOOGLE_TASKS_BASE}/lists/{TASKLIST_ID}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"status": "completed"}
            ) as r:
                return await r.json()

google_tasks = GarcarGoogleTasks()

async def handle_create_task(event):
    await google_tasks.create_task(event["title"], event.get("notes", ""), event.get("due_days", 1))

bus.subscribe("google_tasks.create", handle_create_task)
