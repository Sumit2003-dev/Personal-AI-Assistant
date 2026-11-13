"""
SAM - Main Application Entry Point & Orchestrator
Launches SAM in Desktop mode, CLI mode, or executes autonomous workflows directly.
"""

import sys
import argparse
import asyncio
from pathlib import Path
import logging

from sam.config.settings import settings
from sam.monitoring.system_monitor import system_monitor
from sam.integrations.app_registry import app_registry
from sam.planner.task_planner import task_planner
from sam.executor.task_executor import task_executor
from sam.agent.models_provider import model_manager
from sam.security.permissions import security_gatekeeper
from sam.memory.sqlite_memory import memory_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sam.app")


def print_banner():
    banner = r"""
  ███████╗ █████╗ ███╗   ███╗
  ██╔════╝██╔══██╗████╗ ████║
  ███████╗███████║██╔████╔██║
  ╚════██║██╔══██║██║╚██╔╝██║
  ███████║██║  ██║██║ ╚═╝ ██║
  ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝
  AUTONOMOUS AI COMPUTER OPERATOR
  HP OMEN 16 • Windows 11 • RTX 4050 6GB • Qwen3 4B
    """
    print(banner)


def execute_objective(objective: str):
    """Plans and executes an objective from start to verified completion."""
    print(f"\n[SAM MISSION] Objective: {objective}")
    task = task_planner.plan(objective)
    print(f"[SAM PLANNER] Generated {len(task.steps)} verified steps for Task ID: {task.task_id}:")
    for s in task.steps:
        print(f"  {s.step_index + 1}. {s.title} (Tool: {s.tool_name}, Risk: {s.risk_level.value})")

    completed_task = task_executor.execute_task(task)
    print(f"\n[SAM EXECUTION RESULT]")
    print(f"Status: {completed_task.status.value}")
    print(f"Progress: {completed_task.progress_percentage()}%")
    if completed_task.verification_result:
        print(f"Verification: {'VERIFIED' if completed_task.verification_result.verified else 'FAILED'}")
        print(f"Details: {completed_task.verification_result.details}")
    if completed_task.artifacts:
        print("Generated Artifacts:")
        for art in completed_task.artifacts:
            print(f" - {art}")
    if completed_task.error_details:
        print(f"Error: {completed_task.error_details}")
    return completed_task


def run_workflow(workflow_id: str):
    prompts = {
        "A": "Open VS Code, create a Python project, write a script, run it and fix errors.",
        "B": "Open a selected video, create a vertical 1080p edit, add generated subtitles and export the finished video.",
        "C": "Open a browser, research a topic, collect information and prepare a report.",
        "D": "Check my laptop's CPU, RAM, GPU and disk usage and explain any issues.",
        "E": "Open my selected PDF, summarize it and answer questions about its contents.",
    }
    obj = prompts.get(workflow_id.upper())
    if not obj:
        print(f"Unknown workflow '{workflow_id}'. Available: A, B, C, D, E")
        return
    execute_objective(obj)


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="SAM - Autonomous AI Computer Operator")
    parser.add_argument("--mode", choices=["desktop", "cli", "status"], default="desktop", help="Operating mode")
    parser.add_argument("--goal", type=str, help="Natural language goal to execute")
    parser.add_argument("--workflow", choices=["A", "B", "C", "D", "E"], help="Run preset acceptance workflow")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Desktop server host")
    parser.add_argument("--port", type=int, default=8765, help="Desktop server port")

    args = parser.parse_args()

    if args.workflow:
        run_workflow(args.workflow)
        return

    if args.goal:
        execute_objective(args.goal)
        return

    if args.mode == "status":
        telemetry = system_monitor.get_full_telemetry()
        health = system_monitor.analyze_health()
        print("\n--- SYSTEM STATUS & HEALTH ---")
        print(f"CPU: {telemetry['cpu']['cpu_percent_overall']}%")
        print(f"RAM: {telemetry['ram']['used_percent']}% ({telemetry['ram']['used_gb']} GB / {telemetry['ram']['total_gb']} GB)")
        gpu = telemetry['gpu']
        if gpu.get('available'):
            print(f"GPU: {gpu['name']} ({gpu['vram_used_mb']} MB / {gpu['vram_total_mb']} MB VRAM, Temp: {gpu['temperature_c']}°C)")
        print("\nHealth Diagnostics:")
        for diag in health["diagnostics"]:
            print(f" - {diag}")
        return

    # Default: Desktop Mode
    print(f"\n[SAM DESKTOP] Launching Desktop Interface at http://{args.host}:{args.port}")
    from sam.desktop.web_desktop import run_desktop_server
    run_desktop_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
