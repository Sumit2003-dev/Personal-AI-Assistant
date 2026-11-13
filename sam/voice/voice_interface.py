"""
SAM - Voice Control & Real-Time Audio Interface
Provides real microphone recording, faster-whisper speech recognition,
and Windows SAPI speech synthesis with sounddevice playback and interruption.
"""

from typing import Optional, Callable, Dict, Any
from pathlib import Path
import logging
import io
import numpy as np

from sam.config.settings import settings

logger = logging.getLogger("sam.voice")


class VoiceInterface:
    """Manages real audio capture, STT transcription, and TTS speech synthesis with interruption."""

    def __init__(self):
        self.wake_phrase: str = settings.voice.wake_phrase
        self.is_listening: bool = False
        self.push_to_talk_active: bool = False
        self._on_speech_recognized: Optional[Callable[[str], None]] = None
        self._whisper_model = None

    def _get_whisper_model(self):
        """Lazily load the faster-whisper model from D:\\Whisper\\models."""
        if self._whisper_model is None:
            try:
                import faster_whisper
                download_root = r"D:\Whisper\models"
                logger.info(f"Loading faster-whisper (tiny.en) model from {download_root}...")
                self._whisper_model = faster_whisper.WhisperModel(
                    "tiny.en",
                    device="cpu",
                    compute_type="int8",
                    download_root=download_root
                )
                logger.info("faster-whisper model initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to load faster-whisper model: {e}")
        return self._whisper_model

    def start_listening(self):
        self.is_listening = True
        logger.info(f"Voice interface listening. Wake phrase: '{self.wake_phrase}'")

    def stop_listening(self):
        self.is_listening = False
        logger.info("Voice interface stopped listening.")

    def trigger_push_to_talk(self, pressed: bool):
        self.push_to_talk_active = pressed
        if pressed:
            logger.info("Push-to-talk ACTIVE.")
        else:
            logger.info("Push-to-talk RELEASED.")

    def record_microphone(self, duration: float = 8.0, sample_rate: int = 16000, device: Optional[int] = None) -> Optional[np.ndarray]:
        """Records real microphone audio into a float32 numpy array."""
        try:
            import sounddevice as sd
            logger.info(f"Recording audio from microphone (device={device or sd.default.device[0]}) for {duration} seconds at {sample_rate} Hz...")
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=device
            )
            sd.wait()
            return recording.flatten()
        except Exception as e:
            logger.error(f"Microphone recording failed: {e}")
            return None

    def transcribe(self, audio: Any) -> str:
        """
        Transcribes audio using local faster-whisper model.
        Accepts a float32 numpy array, bytes, or file path.
        """
        try:
            model = self._get_whisper_model()
            if model is None:
                logger.error("Whisper model is not available.")
                return ""

            if isinstance(audio, bytes):
                import scipy.io.wavfile as wavfile
                rate, data = wavfile.read(io.BytesIO(audio))
                float_audio = data.astype(np.float32) / 32768.0 if data.dtype == np.int16 else data.astype(np.float32)
            elif isinstance(audio, (str, Path)):
                import scipy.io.wavfile as wavfile
                rate, data = wavfile.read(str(audio))
                float_audio = data.astype(np.float32) / 32768.0 if data.dtype == np.int16 else data.astype(np.float32)
            elif isinstance(audio, np.ndarray):
                float_audio = audio.flatten().astype(np.float32)
            else:
                logger.error(f"Unsupported audio type for transcription: {type(audio)}")
                return ""

            # Normalize speech amplitude if audio contains signal above ambient floor
            peak = float(np.max(np.abs(float_audio))) if len(float_audio) > 0 else 0.0
            if peak >= 0.002:
                float_audio = (float_audio / peak) * 0.7

            segments, info = model.transcribe(float_audio)
            text = " ".join([s.text.strip() for s in segments]).strip()
            logger.info(f"Transcribed audio ({len(float_audio)} samples, peak={peak:.4f}): '{text}'")
            return text
        except Exception as e:
            logger.error(f"Speech transcription failed: {e}")
            return ""

    def synthesize_to_wav(self, text: str, output_path: str) -> bool:
        """Synthesizes speech to a local WAV file using Windows native SAPI."""
        try:
            import subprocess
            escaped = text.replace("'", "''").replace('"', '`"')
            ps_cmd = (
                f"$voice = New-Object -ComObject SAPI.SpVoice; "
                f"$stream = New-Object -ComObject SAPI.SpFileStream; "
                f"$stream.Open('{output_path}', 3, $false); "
                f"$voice.AudioOutputStream = $stream; "
                f"$voice.Speak('{escaped}'); "
                f"$stream.Close()"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=15.0
            )
            return res.returncode == 0 and Path(output_path).exists()
        except Exception as e:
            logger.error(f"Speech synthesis error: {e}")
            return False

    def speak_text(self, text: str, block: bool = False) -> bool:
        """Synthesizes speech and plays it through the audio output with interruption support."""
        try:
            import sounddevice as sd
            import scipy.io.wavfile as wavfile

            wav_path = Path("sam/data/last_speech.wav").resolve()
            success = self.synthesize_to_wav(text, str(wav_path))

            if not success or not wav_path.exists():
                # Direct fallback to async PowerShell SAPI speak
                import subprocess
                escaped = text.replace("'", "''")
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", f"$v = New-Object -ComObject SAPI.SpVoice; $v.Speak('{escaped}')"],
                    shell=False
                )
                return True

            rate, data = wavfile.read(str(wav_path))
            sd.play(data, rate)
            if block:
                sd.wait()
            return True
        except Exception as e:
            logger.error(f"Speech playback failed: {e}")
            return False

    def interrupt_speech(self):
        """Immediately stops audio playback."""
        try:
            import sounddevice as sd
            sd.stop()
            logger.info("Audio playback interrupted by user.")
        except Exception as e:
            logger.warning(f"Error interrupting audio: {e}")

    def detect_wake_word(self, transcript: str) -> bool:
        """Checks if the wake phrase is present in the transcript."""
        clean = transcript.lower()
        return self.wake_phrase.lower() in clean or "sam" in clean

    def get_status(self) -> Dict[str, Any]:
        has_whisper = self._whisper_model is not None or Path(r"D:\Whisper\models").exists()
        return {
            "wake_phrase": self.wake_phrase,
            "wake_word_enabled": settings.voice.wake_word_enabled,
            "is_listening": self.is_listening,
            "push_to_talk_active": self.push_to_talk_active,
            "stt_engine": "faster-whisper (tiny.en)" if has_whisper else "unavailable",
            "tts_engine": "Windows SAPI (Microsoft David/Zira)",
            "status": "READY" if has_whisper else "DEGRADED",
        }


voice_interface = VoiceInterface()
