"""
SAM - Desktop Web Interface Server (FastAPI)
Provides the complete, interactive dark AI workstation desktop interface,
live screen streaming, task management, voice controls, and dedicated workspaces.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
import io
import time
import os
import uvicorn
import numpy as np
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from sam.config.settings import settings
from sam.monitoring.system_monitor import system_monitor
from sam.planner.task_planner import task_planner
from sam.executor.task_executor import task_executor
from sam.security.permissions import security_gatekeeper
from sam.security.audit import audit_logger
from sam.integrations.app_registry import app_registry
from sam.memory.sqlite_memory import memory_store
from sam.vision.screen_observer import screen_observer
from sam.voice.voice_interface import voice_interface
from sam.coding.coding_agent import coding_agent
from sam.video.video_pipeline import video_pipeline
from sam.browser.browser_agent import browser_agent
from sam.documents.doc_engine import document_engine
from sam.agent.models_provider import model_manager
from sam.computer_use.window import window_manager

app = FastAPI(title="SAM Desktop Interface", version="2.0.0")

# Mount static files
STATIC_DIR = settings.base_dir / "sam" / "desktop" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
TEMPLATES_DIR = settings.base_dir / "sam" / "desktop" / "templates"


# ---------------------------------------------------------
# Request Models
# ---------------------------------------------------------
class TaskCreateRequest(BaseModel):
    objective: str
    context: Dict[str, Any] = {}

class ChatMessageRequest(BaseModel):
    message: str
    context: Dict[str, Any] = {}

class VoiceRecordRequest(BaseModel):
    device_id: Optional[int] = None
    duration: float = 6.0

class CodeWriteRequest(BaseModel):
    workspace: str
    filename: str
    content: str

class CodeRunRequest(BaseModel):
    workspace: str
    filename: str
    args: List[str] = []

class VideoRenderRequest(BaseModel):
    source_filename: Optional[str] = None
    target_width: int = 1080
    target_height: int = 1920

class BrowserResearchRequest(BaseModel):
    query: str
    url: Optional[str] = None

class DocumentSummarizeRequest(BaseModel):
    workspace: str
    filename: str

class CodingRollbackRequest(BaseModel):
    workspace: str = "default_project"
    filename: str

class CodingTestRequest(BaseModel):
    workspace: str = "default_project"
    pattern: str = "test*.py"

class BrowserSearchRequest(BaseModel):
    query: str
    max_results: int = 5

class BrowserLinksRequest(BaseModel):
    url: str

class BrowserSubmitRequest(BaseModel):
    url: str
    form_data: Dict[str, Any] = {}
    method: str = "POST"

class DocumentExportRequest(BaseModel):
    file_path: Optional[str] = None
    format: str = "md"

class MemoryCreateRequest(BaseModel):
    category: str
    key: str
    value: Any

class ModelSelectRequest(BaseModel):
    model_name: str


# ---------------------------------------------------------
# Web Views
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h3>index.html not found</h3>", status_code=404)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ---------------------------------------------------------
# System Telemetry & Health
# ---------------------------------------------------------
@app.get("/api/telemetry")
def get_telemetry():
    return JSONResponse(system_monitor.get_full_telemetry())

@app.get("/api/telemetry/health")
def get_telemetry_health():
    return JSONResponse(system_monitor.analyze_health())

@app.get("/api/applications")
async def list_applications():
    return JSONResponse(app_registry.list_applications())


# ---------------------------------------------------------
# Chat & Autonomous Task Execution
# ---------------------------------------------------------
@app.get("/api/chat/history")
async def get_chat_history():
    messages = memory_store.get_recent_messages(limit=50)
    return JSONResponse({"messages": messages})

@app.post("/api/chat/clear")
async def clear_chat_history():
    memory_store.clear_chat_history()
    return JSONResponse({"success": True})

@app.post("/api/chat")
async def send_chat_message(req: ChatMessageRequest):
    msg = req.message.strip()
    if not msg:
        return JSONResponse({"error": "Message cannot be empty."}, status_code=400)

    memory_store.log_message("user", msg)

    # Autonomous planning via task planner offloaded to threadpool
    task = await run_in_threadpool(task_planner.plan, msg, context=req.context)
    memory_store.record_task(task.to_dict())

    # Log plan to audit trail
    audit_logger.log_event(
        event_type="TASK_CREATED",
        action="chat_task_plan",
        risk_level="LOW",
        status="PLANNING",
        details={"objective": task.objective, "steps_count": len(task.steps)},
        task_id=task.task_id
    )

    # Launch task asynchronously
    asyncio.create_task(task_executor.execute_task_async(task))

    reply_content = f"Task [{task.task_id}] planned by {task.context_data.get('planned_by', 'Local Planner')} with {len(task.steps)} verified steps."
    memory_store.log_message("sam", reply_content, metadata={"task_id": task.task_id})

    return JSONResponse({
        "success": True,
        "task_id": task.task_id,
        "objective": task.objective,
        "status": task.status.value,
        "planned_by": task.context_data.get("planned_by", "Local Planner"),
        "llm_used": task.context_data.get("llm_used", False),
        "steps_count": len(task.steps),
        "steps": [s.to_dict() for s in task.steps]
    })

@app.post("/api/tasks/create")
async def create_task(req: TaskCreateRequest):
    task = await run_in_threadpool(task_planner.plan, req.objective, req.context)
    memory_store.log_message("user", req.objective)
    memory_store.record_task(task.to_dict())
    asyncio.create_task(task_executor.execute_task_async(task))
    return JSONResponse({
        "task_id": task.task_id,
        "objective": task.objective,
        "status": task.status.value,
        "steps_count": len(task.steps),
    })

@app.get("/api/tasks/history")
async def get_tasks_history():
    tasks = memory_store.get_recent_tasks(limit=25)
    return JSONResponse({"tasks": tasks})

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = task_executor._active_tasks.get(task_id)
    if not task:
        # Check SQLite history
        all_recent = memory_store.get_recent_tasks(limit=50)
        matched = next((t for t in all_recent if t["task_id"] == task_id), None)
        if matched:
            return JSONResponse(matched)
        return JSONResponse({"error": "Task not found"}, status_code=404)
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


# ---------------------------------------------------------
# Computer Screen & Live Window Tracking
# ---------------------------------------------------------
@app.get("/api/computer/screenshot/image")
def get_screenshot_image():
    """Captures and returns the live desktop screen as an image."""
    img, _ = screen_observer.capture_fullscreen(save=False)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/jpeg")

@app.get("/api/computer/active_window")
def get_active_window():
    fg = window_manager.get_foreground_window()
    return JSONResponse({
        "hwnd": fg.get("hwnd", 0),
        "title": fg.get("title", ""),
        "pid": fg.get("pid", 0),
        "rect": fg.get("rect", {}),
        "emergency_stop_active": security_gatekeeper.is_emergency_stop_active
    })

@app.get("/api/computer/screenshot")
def get_screenshot_info():
    img, path = screen_observer.capture_fullscreen(save=True)
    return JSONResponse({"success": True, "path": str(path) if path else ""})


# ---------------------------------------------------------
# Voice Controls (Decoupled, Editable, Reliable)
# ---------------------------------------------------------
@app.get("/api/voice/devices")
async def list_voice_devices():
    devices = []
    default_id = -1
    preferred_id, preferred_info = voice_interface.find_preferred_device()
    try:
        import sounddevice as sd
        raw = sd.query_devices()
        default_id = sd.default.device[0]
        for idx, d in enumerate(raw):
            if d.get("max_input_channels", 0) > 0:
                name_clean = d["name"]
                is_airdopes = "airdopes" in name_clean.lower()
                is_intel = "intel" in name_clean.lower() or "smart sound" in name_clean.lower()
                devices.append({
                    "id": idx,
                    "name": name_clean,
                    "channels": d["max_input_channels"],
                    "is_default": (idx == default_id),
                    "is_airdopes": is_airdopes,
                    "is_intel": is_intel,
                    "is_preferred": is_airdopes,
                })
    except Exception as e:
        return JSONResponse({"devices": [], "default_id": -1, "error": str(e)})
    return JSONResponse({
        "devices": devices,
        "default_id": default_id,
        "preferred_device": "boAt Airdopes 131",
        "preferred_info": preferred_info,
    })

@app.post("/api/voice/record")
def record_voice_sample(req: VoiceRecordRequest):
    """
    Records speech from chosen microphone and returns structured result for user review.
    Does NOT auto-execute to prevent accidental triggers or hallucinations from starting tasks.
    """
    try:
        dur = max(1.0, min(req.duration, 15.0))
        audio = voice_interface.record_microphone(duration=dur, device=req.device_id)
        if audio is None or len(audio) == 0:
            return JSONResponse({
                "success": False,
                "error": "Microphone recording returned no audio samples. Check device permissions."
            })

        result = voice_interface.transcribe_structured(audio)

        return JSONResponse({
            "success": True,
            "is_valid": result.is_valid,
            "reliable": result.is_valid,
            "transcript": result.text,
            "editable_transcript": result.text,
            "confidence": result.confidence,
            "rejection_reason": result.rejection_reason,
            "ready_for_submission": result.is_valid,
            "audio_metrics": result.audio_metrics,
            "segments": result.segments,
            "duration": dur,
            "message": "Transcription verified. Review and edit before submitting." if result.is_valid else (result.rejection_reason or "Low confidence audio rejected.")
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/voice/push_to_talk")
async def trigger_ptt(pressed: bool = False):
    voice_interface.trigger_push_to_talk(pressed)
    return JSONResponse({"push_to_talk_active": voice_interface.push_to_talk_active})


# ---------------------------------------------------------
# Coding Agent Workspace
# ---------------------------------------------------------
@app.get("/api/coding/workspaces")
async def list_coding_workspaces():
    ws_dir = settings.data_dir / "workspaces"
    ws_dir.mkdir(parents=True, exist_ok=True)
    dirs = [d.name for d in ws_dir.iterdir() if d.is_dir()]
    if not dirs:
        dirs = ["default_project"]
        (ws_dir / "default_project").mkdir(parents=True, exist_ok=True)
    return JSONResponse({"workspaces": dirs})

@app.get("/api/coding/files")
async def list_coding_files(workspace: str = "default_project"):
    info = coding_agent.inspect_workspace(workspace)
    return JSONResponse(info)

@app.get("/api/coding/read")
async def read_coding_file(workspace: str, filename: str):
    try:
        content = coding_agent.read_file(workspace, filename)
        return JSONResponse({"success": True, "workspace": workspace, "filename": filename, "content": content})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)

@app.post("/api/coding/write")
def write_coding_file(req: CodeWriteRequest):
    try:
        path = coding_agent.write_file(req.workspace, req.filename, req.content)
        return JSONResponse({"success": True, "path": str(path)})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/coding/run")
def run_coding_script(req: CodeRunRequest):
    res = coding_agent.run_script(req.workspace, req.filename, args=req.args)
    return JSONResponse(res)

@app.post("/api/coding/rollback")
def rollback_coding_file(req: CodingRollbackRequest):
    try:
        success = coding_agent.rollback_file(req.workspace, req.filename)
        if success:
            return JSONResponse({"success": True, "message": f"Successfully rolled back {req.filename} from checkpoint."})
        return JSONResponse({"success": False, "error": f"No checkpoint backup found for {req.filename}"}, status_code=404)
    except (FileNotFoundError, PermissionError) as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)

@app.post("/api/coding/test")
def run_coding_tests(req: CodingTestRequest):
    res = coding_agent.run_tests(req.workspace, req.pattern)
    return JSONResponse(res)


# ---------------------------------------------------------
# Video Editor Workspace
# ---------------------------------------------------------
@app.get("/api/video/exports")
async def list_video_exports():
    export_dir = settings.data_dir / "video_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for f in export_dir.glob("*.mp4"):
        files.append({
            "name": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "modified": f.stat().st_mtime
        })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return JSONResponse({"exports": files})

@app.post("/api/video/render")
def render_video_workflow(req: VideoRenderRequest):
    source_path = None
    if req.source_filename:
        src = settings.data_dir / "video_exports" / req.source_filename
        if src.exists():
            source_path = str(src)
    res = video_pipeline.execute_vertical_workflow(source_path=source_path)
    return JSONResponse(res)


# ---------------------------------------------------------
# Browser Agent Workspace
# ---------------------------------------------------------
@app.post("/api/browser/research")
def browser_research(req: BrowserResearchRequest):
    target_url = req.url or f"https://en.wikipedia.org/wiki/{req.query}"
    res = browser_agent.fetch_page_content(target_url)
    return JSONResponse({
        "success": True,
        "query": req.query,
        "url": target_url,
        "title": res.get("title", "Research Summary"),
        "content_sample": res.get("content_sample", "")
    })

@app.post("/api/browser/search")
def browser_search(req: BrowserSearchRequest):
    res = browser_agent.search_web(req.query, req.max_results)
    return JSONResponse(res)

@app.post("/api/browser/links")
def browser_links(req: BrowserLinksRequest):
    res = browser_agent.extract_links(req.url)
    return JSONResponse(res)

@app.post("/api/browser/submit")
def browser_submit(req: BrowserSubmitRequest):
    res = browser_agent.submit_form(req.url, req.form_data, req.method)
    status_code = 403 if res.get("requires_approval") else (200 if res.get("success") else 400)
    return JSONResponse(res, status_code=status_code)


# ---------------------------------------------------------
# Document Intelligence & File Explorer
# ---------------------------------------------------------
@app.get("/api/documents/list")
async def list_documents(workspace: str = "default_project"):
    ws_dir = settings.data_dir / "workspaces" / workspace
    ws_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for p in ws_dir.glob("*"):
        if p.is_file():
            docs.append({
                "name": p.name,
                "extension": p.suffix.lower(),
                "size_kb": round(p.stat().st_size / 1024, 1),
                "modified": p.stat().st_mtime
            })
    return JSONResponse({"workspace": workspace, "documents": docs})

@app.post("/api/documents/summarize")
def summarize_document_api(req: DocumentSummarizeRequest):
    path = settings.data_dir / "workspaces" / req.workspace / req.filename
    if not path.exists():
        return JSONResponse({"error": f"File '{req.filename}' not found."}, status_code=404)
    res = document_engine.summarize_document(str(path))
    return JSONResponse(res)

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), workspace: str = Form("default_project")):
    ws_dir = settings.data_dir / "workspaces" / workspace
    ws_dir.mkdir(parents=True, exist_ok=True)
    dest = ws_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return JSONResponse({"success": True, "filename": file.filename, "size_bytes": len(content)})

@app.post("/api/documents/export")
def export_document_analysis(req: DocumentExportRequest):
    path = document_engine.export_analysis(req.file_path, req.format)
    return JSONResponse({"success": True, "exported_path": str(path)})


# ---------------------------------------------------------
# Memory Workspace (CRUD)
# ---------------------------------------------------------
@app.get("/api/memory")
async def get_all_memories():
    return JSONResponse({"memories": memory_store.list_all_memories()})

@app.get("/api/memory/search")
async def search_memories(query: str = ""):
    results = memory_store.search_memories(query)
    return JSONResponse({"memories": results})

@app.post("/api/memory")
async def set_memory(req: MemoryCreateRequest):
    ok = memory_store.set_memory(req.category, req.key, req.value)
    return JSONResponse({"success": ok})

@app.delete("/api/memory/{key}")
async def delete_memory(key: str):
    ok = memory_store.delete_memory(key)
    return JSONResponse({"success": ok})


# ---------------------------------------------------------
# Settings, Local LLM & Security
# ---------------------------------------------------------
@app.get("/api/models/status")
async def get_models_status():
    return JSONResponse(model_manager.get_status())

@app.post("/api/models/select")
async def select_model(req: ModelSelectRequest):
    model_manager.ollama.model = req.model_name
    return JSONResponse({
        "selected_model": req.model_name,
        "status": model_manager.get_status()
    })

@app.get("/api/security/audit_logs")
async def get_audit_logs(limit: int = 50):
    logs = audit_logger.read_recent_logs(limit=limit)
    return JSONResponse({"logs": logs})

@app.post("/api/emergency_stop")
async def trigger_emergency_stop():
    security_gatekeeper.trigger_emergency_stop("Desktop UI Emergency Trigger")
    return JSONResponse({"status": "EMERGENCY_STOP_ACTIVATED", "active": True})

@app.post("/api/security/reset_emergency_stop")
async def reset_emergency_stop():
    security_gatekeeper.reset_emergency_stop()
    return JSONResponse({"status": "EMERGENCY_STOP_RESET", "active": False})


# ---------------------------------------------------------
# Server Launch Helper
# ---------------------------------------------------------
def run_desktop_server(host: str = "127.0.0.1", port: int = 8765):
    """Runs the FastAPI Desktop interface."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_desktop_server()
