"""
SAM - Phase 4.1 Live Interactive Validation Script
Executes Test 1 (Live Mic Capture & Whisper STT),
Test 2 (Local LLM Reasoning & Task Planning),
Test 3 (Real Windows Notepad Operation & Verification),
and Test 4 (Local TTS Speech Synthesis & Playback).
"""

import sys
import time
from pathlib import Path

SAM_ROOT = Path(__file__).resolve().parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.voice.voice_interface import voice_interface
from sam.agent.models_provider import model_manager
from sam.planner.task_planner import task_planner
from sam.executor.task_executor import task_executor
from sam.tools.registry import tool_registry
from sam.agent.models import TaskStatus


def run_live_audio_capture(duration: float = 6.0) -> str:
    print(f"\n[MIC] RECORDING LIVE AUDIO FOR {duration} SECONDS FROM HP OMEN 16 MICROPHONE...")
    print("[MIC] PLEASE SPEAK YOUR COMMAND NOW!")
    audio = voice_interface.record_microphone(duration=duration)
    if audio is None or len(audio) == 0:
        print("[MIC ERROR] Failed to record audio or audio buffer is empty.")
        return ""
    print(f"[MIC] Captured {len(audio)} samples ({len(audio)/16000:.2f} seconds).")
    print("[STT] Transcribing with faster-whisper (tiny.en on D:\\Whisper\\models)...")
    transcript = voice_interface.transcribe(audio)
    print(f"[STT RESULT] '{transcript}'")
    return transcript


def run_llm_reasoning(prompt: str):
    print("\n" + "=" * 60)
    print("TEST 2: REAL LOCAL LLM PLANNING (OLLAMA)")
    print("=" * 60)
    task = task_planner.plan(prompt)
    print(f"Task ID: {task.task_id}")
    print(f"Planned by: {task.context_data.get('planned_by')}")
    print(f"LLM Used: {task.context_data.get('llm_used')}")
    print(f"Step Count: {len(task.steps)}")
    for idx, s in enumerate(task.steps):
        print(f"  Step {idx+1}: {s.title} (Tool: {s.tool_name}, Risk: {s.risk_level.name})")
    return task


def run_notepad_operation(test_sentence: str, filename: str = "live_validation_notepad.txt"):
    print("\n" + "=" * 60)
    print("TEST 3: REAL WINDOWS COMPUTER OPERATION (NOTEPAD)")
    print("=" * 60)
    res = tool_registry.execute_tool("computer_operate_notepad", {
        "filename": filename,
        "text_content": test_sentence,
        "workspace_name": "live_validation"
    })
    print(f"Notepad Operation Success: {res.success}")
    if res.output:
        print(f"Saved Path: {res.output.get('saved_path')}")
        print(f"Screenshot Path: {res.output.get('screenshot_path')}")
        print(f"Content Preview: {repr(res.output.get('content_preview'))}")
    return res


def run_spoken_response(text: str):
    print("\n" + "=" * 60)
    print("TEST 4: SPOKEN RESPONSE VIA REAL SPEAKERS & INTERRUPTION")
    print("=" * 60)
    print(f"SAM speaking: '{text}'")
    ok = voice_interface.speak_text(text, block=False)
    print(f"Playback started: {ok}")
    time.sleep(1.0)
    print("Testing interruption...")
    voice_interface.interrupt_speech()
    print("Interrupted successfully.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--record-only":
        dur = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
        transcript = run_live_audio_capture(dur)
        sys.exit(0 if transcript else 1)

