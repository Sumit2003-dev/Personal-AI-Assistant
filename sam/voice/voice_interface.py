"""
SAM - Voice Control & Real-Time Audio Interface
Provides real microphone recording, faster-whisper speech recognition,
audio health metrics (RMS, peak, clipping, silence duration), and Windows SAPI speech synthesis.
Preserves user's preferred boAt Airdopes 131 microphone and rejects low-confidence/hallucinated transcripts.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Dict, Any, List, Tuple
from pathlib import Path
import logging
import io
import time
import numpy as np

from sam.config.settings import settings

logger = logging.getLogger("sam.voice")

HALLUCINATION_PATTERNS = {
    "you", "you.", "thank you", "thank you.", "thanks", "thanks for watching",
    "bye", "bye.", "okay", "so", ".", "subtitles by", "mbc", "subscribe",
    "see you next time", "hello", "the end", "amara.org"
}


@dataclass
class AudioMetrics:
    rms: float
    peak: float
    clipping_ratio: float
    silence_ratio: float
    duration_seconds: float
    sample_count: int
    is_silent: bool


@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    is_valid: bool
    rejection_reason: Optional[str] = None
    audio_metrics: Dict[str, Any] = field(default_factory=dict)
    segments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VoiceInterface:
    """Manages real audio capture, STT transcription, and TTS speech synthesis with interruption."""

    def __init__(self):
        self.wake_phrase: str = settings.voice.wake_phrase
        self.is_listening: bool = False
        self.push_to_talk_active: bool = False
        self._on_speech_recognized: Optional[Callable[[str], None]] = None
        self._whisper_model = None
        self._preferred_device_name: str = settings.voice.preferred_device_name

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

    def calculate_audio_metrics(self, float_audio: np.ndarray, sample_rate: int = 16000) -> AudioMetrics:
        """Calculates RMS, peak amplitude, clipping percentage, and silence ratio."""
        if len(float_audio) == 0:
            return AudioMetrics(
                rms=0.0,
                peak=0.0,
                clipping_ratio=0.0,
                silence_ratio=1.0,
                duration_seconds=0.0,
                sample_count=0,
                is_silent=True,
            )

        peak = float(np.max(np.abs(float_audio)))
        rms = float(np.sqrt(np.mean(float_audio**2)))
        clipping = float(np.sum(np.abs(float_audio) >= settings.voice.clipping_threshold)) / len(float_audio)
        duration = float(len(float_audio)) / sample_rate

        # 20ms frames for silence estimation
        frame_size = max(1, int(sample_rate * 0.02))
        n_frames = len(float_audio) // frame_size
        if n_frames > 0:
            frames = float_audio[: n_frames * frame_size].reshape((n_frames, frame_size))
            frame_rms = np.sqrt(np.mean(frames**2, axis=1))
            silent_frames = np.sum(frame_rms < settings.voice.silence_rms_threshold)
            silence_ratio = float(silent_frames) / n_frames
        else:
            silence_ratio = 1.0 if rms < settings.voice.silence_rms_threshold else 0.0

        is_silent = (
            (rms < settings.voice.silence_rms_threshold)
            or (peak < settings.voice.min_peak_amplitude)
            or (silence_ratio >= 0.90 and peak < 0.06)
        )

        return AudioMetrics(
            rms=round(rms, 6),
            peak=round(peak, 6),
            clipping_ratio=round(clipping, 6),
            silence_ratio=round(silence_ratio, 4),
            duration_seconds=round(duration, 3),
            sample_count=len(float_audio),
            is_silent=is_silent,
        )

    def find_preferred_device(self) -> Tuple[Optional[int], Dict[str, Any]]:
        """
        Locates the user's preferred microphone (boAt Airdopes 131).
        Preserves preference without permanently overwriting with Intel Smart Sound.
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            target_pref = self._preferred_device_name.lower()
            airdopes_idx = None
            intel_idx = None
            default_id = sd.default.device[0]

            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    name_l = d["name"].lower()
                    if "airdopes" in name_l:
                        airdopes_idx = idx
                    elif "intel" in name_l or "smart sound" in name_l:
                        intel_idx = idx

            if airdopes_idx is not None:
                caps = self.verify_device_capabilities(airdopes_idx)
                return airdopes_idx, {
                    "device_id": airdopes_idx,
                    "name": devices[airdopes_idx]["name"],
                    "preferred": True,
                    "is_active": True,
                    "capabilities": caps,
                }
            else:
                return None, {
                    "preferred_name": self._preferred_device_name,
                    "preferred": True,
                    "is_active": False,
                    "status": "DISCONNECTED",
                    "message": f"{self._preferred_device_name} is currently offline. Preference preserved.",
                    "temporary_fallback_id": intel_idx if intel_idx is not None else default_id,
                }
        except Exception as e:
            return None, {"error": str(e), "is_active": False}

    def verify_device_capabilities(self, device_id: int) -> Dict[str, Any]:
        """Queries supported sample rates, channels, and input settings."""
        try:
            import sounddevice as sd
            info = sd.query_devices(device_id)
            test_rates = [16000, 44100, 48000]
            supported_rates = []
            for r in test_rates:
                try:
                    sd.check_input_settings(device=device_id, samplerate=r, channels=1)
                    supported_rates.append(r)
                except Exception:
                    pass
            return {
                "device_id": device_id,
                "name": info.get("name", "Unknown"),
                "max_input_channels": info.get("max_input_channels", 0),
                "default_samplerate": info.get("default_samplerate", 16000),
                "supported_samplerates": supported_rates,
            }
        except Exception as e:
            return {"device_id": device_id, "error": str(e)}

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

    def record_microphone(
        self,
        duration: float = 6.0,
        sample_rate: int = 16000,
        device: Optional[int] = None,
    ) -> Optional[np.ndarray]:
        """Records real microphone audio into a float32 numpy array with error verification."""
        try:
            import sounddevice as sd
            # Auto-resolve preferred device if no explicit device ID passed
            target_device = device
            if target_device is None:
                pref_id, pref_info = self.find_preferred_device()
                if pref_id is not None:
                    target_device = pref_id

            logger.info(
                f"Recording audio (device={target_device if target_device is not None else sd.default.device[0]}) "
                f"for {duration}s at {sample_rate}Hz..."
            )
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=target_device,
            )
            sd.wait()
            return recording.flatten()
        except Exception as e:
            logger.error(f"Microphone recording failed on device {device}: {e}")
            return None

    def transcribe_structured(self, audio: Any) -> TranscriptionResult:
        """
        Transcribes audio with speech energy pre-filtering, segment metadata extraction,
        confidence scoring, and hallucination rejection.
        """
        try:
            float_audio = None
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
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_valid=False,
                    rejection_reason=f"Unsupported audio type: {type(audio)}",
                )

            # 1. Pre-filtering: calculate audio metrics
            metrics = self.calculate_audio_metrics(float_audio)
            if metrics.is_silent:
                logger.info(
                    f"Voice input rejected before transcription: Near-silent recording "
                    f"(RMS={metrics.rms:.5f}, Peak={metrics.peak:.5f}, SilenceRatio={metrics.silence_ratio:.2f})."
                )
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_valid=False,
                    rejection_reason="Audio rejected: near-silent recording or ambient noise only.",
                    audio_metrics=asdict(metrics),
                    segments=[],
                )

            # 2. Prevent artificial noise amplification: Only normalize if valid speech peak exists
            if metrics.peak >= 0.05:
                float_audio = (float_audio / metrics.peak) * 0.7

            # 3. Whisper STT
            model = self._get_whisper_model()
            if model is None:
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_valid=False,
                    rejection_reason="Whisper model unavailable.",
                    audio_metrics=asdict(metrics),
                )

            segments, info = model.transcribe(float_audio)
            seg_list = []
            text_parts = []
            total_logprob = 0.0
            total_no_speech = 0.0

            for s in segments:
                t = s.text.strip()
                if t:
                    text_parts.append(t)
                seg_list.append({
                    "text": t,
                    "start": s.start,
                    "end": s.end,
                    "avg_logprob": s.avg_logprob,
                    "no_speech_prob": s.no_speech_prob,
                })
                total_logprob += s.avg_logprob
                total_no_speech += s.no_speech_prob

            raw_text = " ".join(text_parts).strip()
            n_segs = max(1, len(seg_list))
            avg_logprob = total_logprob / n_segs
            avg_no_speech = total_no_speech / n_segs

            # 4. Filter hallucinated artifacts or accidental single words
            clean_token = raw_text.lower().strip(" .?!,")
            if clean_token in HALLUCINATION_PATTERNS or len(clean_token) <= 1:
                logger.warning(f"Rejected hallucinated Whisper transcript: '{raw_text}'")
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_valid=False,
                    rejection_reason=f"Rejected: Accidental word or hallucinated artifact ('{raw_text}') detected.",
                    audio_metrics=asdict(metrics),
                    segments=seg_list,
                )

            # 5. Low confidence rejection
            if avg_no_speech > settings.voice.max_no_speech_prob or avg_logprob < settings.voice.min_avg_logprob:
                logger.warning(
                    f"Rejected low-confidence transcript '{raw_text}' (no_speech={avg_no_speech:.2f}, logprob={avg_logprob:.2f})"
                )
                return TranscriptionResult(
                    text="",
                    confidence=round(max(0.0, 1.0 - avg_no_speech), 3),
                    is_valid=False,
                    rejection_reason=f"Rejected: Low confidence (no_speech_prob={avg_no_speech:.2f}, avg_logprob={avg_logprob:.2f}).",
                    audio_metrics=asdict(metrics),
                    segments=seg_list,
                )

            conf = round(max(0.0, min(1.0, np.exp(avg_logprob) * (1.0 - avg_no_speech))), 3)
            logger.info(f"Verified voice transcription (conf={conf:.2f}): '{raw_text}'")
            return TranscriptionResult(
                text=raw_text,
                confidence=conf,
                is_valid=True,
                audio_metrics=asdict(metrics),
                segments=seg_list,
            )

        except Exception as e:
            logger.error(f"Speech transcription failed: {e}")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                is_valid=False,
                rejection_reason=f"Internal transcription error: {str(e)}",
            )

    def transcribe(self, audio: Any) -> str:
        """Backward-compatible string transcription returning only verified, high-confidence text."""
        res = self.transcribe_structured(audio)
        return res.text if res.is_valid else ""

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
                import subprocess
                escaped = text.replace("'", "''")
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", f"$v = New-Object -ComObject SAPI.SpVoice; $v.Speak('{escaped}')"],
                    capture_output=True,
                    timeout=10.0,
                    stdin=subprocess.DEVNULL,
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
        pref_id, pref_info = self.find_preferred_device()
        return {
            "wake_phrase": self.wake_phrase,
            "wake_word_enabled": settings.voice.wake_word_enabled,
            "is_listening": self.is_listening,
            "push_to_talk_active": self.push_to_talk_active,
            "stt_engine": "faster-whisper (tiny.en)" if has_whisper else "unavailable",
            "tts_engine": "Windows SAPI (Microsoft David/Zira)",
            "preferred_microphone": self._preferred_device_name,
            "preferred_microphone_info": pref_info,
            "status": "READY" if has_whisper else "DEGRADED",
        }


voice_interface = VoiceInterface()
