"""
Garcar Enterprise — Asana Integration
Project task management: auto-creates and updates Asana tasks from Butler agent events.
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

ASANA_BASE = "https://app.asana.com/api/1.0"
ASANA_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('ASANA_PERSONAL_ACCESS_TOKEN', '')}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

class GarcarAsana:
    async def create_task(self, name: str, notes: str = "", project_gid: str = None, assignee: str = "me") -> dict:
        project = project_gid or os.environ.get("ASANA_PROJECT_REVENUE_GID", "")
        payload = {"data": {
            "name": name,
            "notes": notes,
            "projects": [project],
            "assignee": assignee,
            "workspace": os.environ.get("ASANA_WORKSPACE_ID", "")
        }}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{ASANA_BASE}/tasks",
                              headers=ASANA_HEADERS, json=payload) as r:
                data = await r.json()
                task = data.get("data", {})
                await bus.emit("asana.task_created", {
                    "gid": task.get("gid"), "name": name,
                    "url": f"https://app.asana.com/0/{project}/{task.get('gid')}"
                }, agents=["PMAgent"])
                return task

    async def complete_task(self, task_gid: str) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.put(f"{ASANA_BASE}/tasks/{task_gid}",
                             headers=ASANA_HEADERS, json={"data": {"completed": True}}) as r:
                return (await r.json()).get("data", {})

    async def get_project_tasks(self, project_gid: str = None, completed: bool = False) -> list:
        project = project_gid or os.environ.get("ASANA_PROJECT_REVENUE_GID", "")
        params = {"project": project, "completed_since": "now" if not completed else ""}
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{ASANA_BASE}/tasks",
                             headers=ASANA_HEADERS, params=params) as r:
                data = await r.json()
                return data.get("data", [])

asana = GarcarAsana()

async def handle_create_asana_task(event):
    await asana.create_task(event["name"], event.get("notes", ""), event.get("project_gid"))

bus.subscribe("asana.create_task", handle_create_asana_task)
