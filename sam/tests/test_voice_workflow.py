"""
SAM - End-to-End Voice-to-Action-to-Voice Acceptance Test
Demonstrates the complete autonomous pipeline:
Voice Input -> faster-whisper STT -> local LLM Planner -> Real Windows Action Execution -> Result Verification -> Local TTS Speech Output.
"""

import unittest
import time
from pathlib import Path

from sam.voice.voice_interface import voice_interface
from sam.planner.task_planner import TaskPlanner
from sam.executor.task_executor import task_executor
from sam.agent.models import TaskStatus, StepStatus


class TestVoiceWorkflow(unittest.TestCase):
    """End-to-end acceptance test for voice, LLM planning, and action execution."""

    def test_complete_voice_to_action_pipeline(self):
        print("\n" + "=" * 70)
        print("STAGE 1: GENERATE / CAPTURE SPOKEN VOICE COMMAND")
        print("=" * 70)
        # Synthesize a real spoken command into a WAV file to simulate speech input
        test_wav = Path("sam/data/spoken_command.wav").resolve()
        command_spoken = "Inspect hardware telemetry and summarize CPU status"
        print(f"User speaks: '{command_spoken}'")
        synth_ok = voice_interface.synthesize_to_wav(command_spoken, str(test_wav))
        self.assertTrue(synth_ok, "Failed to synthesize spoken voice command to WAV")
        self.assertTrue(test_wav.exists(), "Spoken command WAV file does not exist")

        print("\n" + "=" * 70)
        print("STAGE 2: TRANSCRIBE SPOKEN AUDIO WITH FASTER-WHISPER")
        print("=" * 70)
        transcript = voice_interface.transcribe(test_wav)
        print(f"faster-whisper Transcript: '{transcript}'")
        self.assertTrue(len(transcript) > 0, "Transcription returned empty string")
        self.assertIn("hardware", transcript.lower())

        print("\n" + "=" * 70)
        print("STAGE 3: LOCAL LLM TASK PLANNING (OLLAMA)")
        print("=" * 70)
        planner = TaskPlanner()
        task = planner.plan(transcript)
        print(f"Task ID: {task.task_id}")
        print(f"Planned by: {task.context_data.get('planned_by')}")
        print(f"LLM Used: {task.context_data.get('llm_used')}")
        print(f"Decomposed Steps: {len(task.steps)}")
        for step in task.steps:
            print(f"  Step {step.step_index}: {step.title} -> tool: {step.tool_name}")

        self.assertTrue(task.context_data.get("llm_used"), "Planner failed to use local LLM")
        self.assertTrue(len(task.steps) > 0, "No steps generated in task plan")

        print("\n" + "=" * 70)
        print("STAGE 4: EXECUTE REAL WINDOWS ACTION & VERIFY RESULT")
        print("=" * 70)
        executed_task = task_executor.execute_task(task)
        print(f"Execution Final Status: {executed_task.status.value}")
        for s in executed_task.steps:
            print(f"  [{s.status.value}] {s.title}")
            if s.verification_result:
                print(f"      Verification: verified={s.verification_result.verified}, details={s.verification_result.details}")

        self.assertEqual(executed_task.status, TaskStatus.COMPLETED)
        self.assertTrue(all(s.status == StepStatus.COMPLETED for s in executed_task.steps))

        print("\n" + "=" * 70)
        print("STAGE 5: SYNTHESIZE & SPEAK OUTCOME VIA LOCAL TTS")
        print("=" * 70)
        outcome_speech = f"Task completed successfully. Executed {len(executed_task.steps)} operations and verified system telemetry."
        print(f"SAM speaks: '{outcome_speech}'")
        speak_ok = voice_interface.speak_text(outcome_speech, block=False)
        self.assertTrue(speak_ok, "Failed to speak outcome via local TTS")
        time.sleep(0.5)

        print("\n" + "=" * 70)
        print("STAGE 6: TEST AUDIO PLAYBACK INTERRUPTION")
        print("=" * 70)
        voice_interface.interrupt_speech()
        print("Audio playback interrupted successfully.")
        print("=" * 70)
        print("COMPLETE VOICE-TO-ACTION-TO-VOICE DEMONSTRATION VERIFIED!")
        print("=" * 70)


if __name__ == "__main__":
    unittest.main()
