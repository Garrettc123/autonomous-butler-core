"""
Garcar Enterprise — ClickUp Integration
Task management: creates, updates, and resolves ClickUp tasks from Butler agent events.
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

CLICKUP_BASE = "https://api.clickup.com/api/v2"
CLICKUP_HEADERS = {
    "Authorization": os.environ.get("CLICKUP_API_TOKEN", ""),
    "Content-Type": "application/json"
}

PRIORITY_MAP = {"urgent": 1, "high": 2, "normal": 3, "low": 4}

class GarcarClickUp:
    async def create_task(self, list_id: str, name: str, description: str = "", priority: str = "normal", tags: list = []) -> dict:
        payload = {
            "name": name,
            "description": description,
            "priority": PRIORITY_MAP.get(priority, 3),
            "tags": tags,
            "status": "to do"
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{CLICKUP_BASE}/list/{list_id}/task",
                              headers=CLICKUP_HEADERS, json=payload) as r:
                data = await r.json()
                await bus.emit("clickup.task_created", {
                    "task_id": data.get("id"), "name": name, "url": data.get("url")
                }, agents=["PMAgent"])
                return data

    async def update_task_status(self, task_id: str, status: str) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.put(f"{CLICKUP_BASE}/task/{task_id}",
                             headers=CLICKUP_HEADERS, json={"status": status}) as r:
                return await r.json()

    async def get_workspace_tasks(self, list_id: str, status: str = None) -> list:
        params = {"statuses[]": status} if status else {}
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{CLICKUP_BASE}/list/{list_id}/task",
                             headers=CLICKUP_HEADERS, params=params) as r:
                data = await r.json()
                return data.get("tasks", [])

clickup = GarcarClickUp()

async def handle_create_clickup_task(event):
    list_id = event.get("list_id", os.environ.get("CLICKUP_LIST_REVENUE_ID", ""))
    await clickup.create_task(list_id, event["name"], event.get("description", ""), event.get("priority", "normal"))

bus.subscribe("clickup.create_task", handle_create_clickup_task)
