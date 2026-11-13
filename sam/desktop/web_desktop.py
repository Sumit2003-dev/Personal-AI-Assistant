"""
SAM - Desktop Web Interface Server (FastAPI + WebSockets)
Provides the full 10-section dark futuristic cyber desktop interface and real-time mission control.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sam.config.settings import settings
from sam.monitoring.system_monitor import system_monitor
from sam.planner.task_planner import task_planner
from sam.executor.task_executor import task_executor
from sam.security.permissions import security_gatekeeper
from sam.integrations.app_registry import app_registry
from sam.memory.sqlite_memory import memory_store
from sam.vision.screen_observer import screen_observer
from sam.voice.voice_interface import voice_interface

app = FastAPI(title="SAM Desktop Interface", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory=str(settings.base_dir / "sam" / "desktop" / "static")), name="static")
TEMPLATES_DIR = settings.base_dir / "sam" / "desktop" / "templates"


class TaskCreateRequest(BaseModel):
    objective: str
    context: Dict[str, Any] = {}


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = TEMPLATES_DIR / "index.html"
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/telemetry")
async def get_telemetry():
    return JSONResponse(system_monitor.get_full_telemetry())


@app.get("/api/telemetry/health")
async def get_telemetry_health():
    return JSONResponse(system_monitor.analyze_health())


@app.get("/api/applications")
async def list_applications():
    return JSONResponse(app_registry.list_applications())


@app.post("/api/tasks/create")
async def create_task(req: TaskCreateRequest, bg_tasks: BackgroundTasks):
    task = task_planner.plan(req.objective, req.context)
    # Save objective to memory
    memory_store.log_message("user", req.objective)

    # Launch task asynchronously via thread bridge
    asyncio.create_task(task_executor.execute_task_async(task))

    return JSONResponse({
        "task_id": task.task_id,
        "objective": task.objective,
        "status": task.status.value,
        "steps_count": len(task.steps),
    })


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = task_executor._active_tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    # Record progress to memory store
    memory_store.record_task(task.to_dict())
    return JSONResponse(task.to_dict())


@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    ok = task_executor.pause_task(task_id)
    return JSONResponse({"success": ok})


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    ok = task_executor.resume_task(task_id)
    task = task_executor._active_tasks.get(task_id)
    if ok and task:
        asyncio.create_task(task_executor.execute_task_async(task))
    return JSONResponse({"success": ok})


@app.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    ok = task_executor.stop_task(task_id)
    return JSONResponse({"success": ok})


@app.post("/api/tasks/{task_id}/approve")
async def approve_step(task_id: str):
    ok = task_executor.approve_pending_step(task_id)
    task = task_executor._active_tasks.get(task_id)
    if ok and task:
        asyncio.create_task(task_executor.execute_task_async(task))
    return JSONResponse({"success": ok})


@app.post("/api/tasks/{task_id}/reject")
async def reject_step(task_id: str):
    ok = task_executor.reject_pending_step(task_id)
    return JSONResponse({"success": ok})


@app.post("/api/emergency_stop")
async def emergency_stop():
    security_gatekeeper.trigger_emergency_stop()
    return JSONResponse({"status": "EMERGENCY_STOP_ACTIVATED"})


@app.post("/api/voice/push_to_talk")
async def push_to_talk(pressed: bool = False):
    voice_interface.trigger_push_to_talk(pressed)
    return JSONResponse(voice_interface.get_status())


@app.get("/api/computer/screenshot")
async def get_screenshot():
    img, path = screen_observer.capture_fullscreen(save=True)
    return JSONResponse({"success": True, "path": str(path) if path else ""})


@app.get("/api/memory")
async def list_memories():
    return JSONResponse(memory_store.list_all_memories())


def run_desktop_server(host: str = "127.0.0.1", port: int = 8765):
    """Runs the FastAPI Desktop interface."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_desktop_server()
