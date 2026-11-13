import sys
import time
import numpy as np
from pathlib import Path
import sounddevice as sd

SAM_ROOT = Path(__file__).resolve().parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.voice.voice_interface import voice_interface
from sam.planner.task_planner import task_planner
from sam.agent.models_provider import model_manager

DURATION = 10.0
SAMPLE_RATE = 16000

# Locate Airdopes 131 device index
devices = sd.query_devices()
target_dev = None
for idx, d in enumerate(devices):
    if "airdopes" in d["name"].lower() and d["max_input_channels"] > 0:
        target_dev = idx
        break

if target_dev is None:
    target_dev = sd.default.device[0]

dev_info = sd.query_devices(target_dev)
print("=" * 65)
print(f"SAM LIVE RECORDING ON: [{target_dev}] {dev_info['name']}")
print(f"DURATION: {DURATION:.0f} SECONDS")
print(">>> SPEAK INTO YOUR AIRDOPES 131 EARBUDS NOW! <<<")
print("=" * 65)

rec = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=target_dev)
sd.wait()
audio = rec.flatten()

peak = float(np.max(np.abs(audio)))
rms = float(np.sqrt(np.mean(audio**2)))
print(f"\n[MIC] Captured {len(audio)} samples ({len(audio)/SAMPLE_RATE:.1f}s)")
print(f"[MIC LEVEL] Peak Amplitude = {peak:.6f}, RMS Volume = {rms:.6f}")

print("\n[STT] Transcribing with local faster-whisper (tiny.en on D:\\Whisper\\models)...")
transcript = voice_interface.transcribe(audio)
print(f"[WHISPER TRANSCRIPT] '{transcript}'")

if transcript:
    print("\n" + "=" * 65)
    print("TEST 2: AUTONOMOUS LOCAL LLM PLANNING (OLLAMA)")
    print("=" * 65)
    task = task_planner.plan(transcript)
    print(f"Task ID: {task.task_id}")
    print(f"Planned by: {task.context_data.get('planned_by')}")
    print(f"LLM Used: {task.context_data.get('llm_used')}")
    print(f"Decomposed Steps: {len(task.steps)}")
    for s in task.steps:
        print(f"  [{s.step_index + 1}] {s.title} -> Tool: {s.tool_name} (Risk: {s.risk_level.name})")
else:
    print("\n[STT NOTICE] Whisper received ambient silence. No words detected.")
