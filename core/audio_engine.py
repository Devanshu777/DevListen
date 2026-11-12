"""
Resilient Audio Ingestion Engine for DevListen.
- Captures User Mic (Channel 0) and System Loopback/Attendees (Channel 1).
- Automatic sample-rate normalization to 16kHz for ML compatibility.
- Fault-tolerant auto-reconnect on device disconnects (AUDCLNT_E_DEVICE_INVALIDATED).
- Gated by Adaptive VAD for near-zero idle resource utilization.
"""
import time
import queue
import threading
import numpy as np
import pyaudiowpatch as pyaudio
from typing import Callable, Optional
from core.ring_buffer import AudioRingBuffer
from core.vad_detector import AdaptiveVAD

class ResilientAudioEngine:
    """
    Manages dual-stream audio capture:
      1. Default Microphone (User speaking)
      2. Default WASAPI Loopback (Interviewer / Attendees speaking in Teams/Zoom/Meet)
    """
    TARGET_SAMPLE_RATE = 16000  # Standard speech recognition rate

    def __init__(
        self,
        on_speech_chunk: Optional[Callable[[np.ndarray, str], None]] = None,
        on_levels_chunk: Optional[Callable[[float, float], None]] = None
    ):
        """
        on_speech_chunk(pcm_data_16k, speaker_source) callback fired when speech is active.
        speaker_source is either "USER" or "REMOTE".
        on_levels_chunk(mic_level, loopback_level) callback fired for real-time VU meter (0.0 to 1.0).
        """
        self.on_speech_chunk = on_speech_chunk
        self.on_levels_chunk = on_levels_chunk
        self.ring_buffer = AudioRingBuffer(capacity_seconds=30, sample_rate=self.TARGET_SAMPLE_RATE, channels=2)
        
        self.vad_user = AdaptiveVAD(sample_rate=self.TARGET_SAMPLE_RATE)
        self.vad_remote = AdaptiveVAD(sample_rate=self.TARGET_SAMPLE_RATE)

        self.is_running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Starts the audio capture watchdog loop."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._supervision_loop, daemon=True, name="DevListen-AudioDaemon")
        self._capture_thread.start()

    def stop(self):
        """Stops audio capture gracefully."""
        self.is_running = False
        self._stop_event.set()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)

    def _supervision_loop(self):
        """
        Supervision watchdog: If an audio device disconnects or throws an error,
        it automatically re-acquires endpoints without crashing the process.
        """
        while self.is_running:
            try:
                self._run_capture_session()
            except Exception as e:
                if not self.is_running:
                    break
                print(f"[DevListen AudioEngine] Stream error ({e}), recovering in 1.5s...")
                time.sleep(1.5)

    def _run_capture_session(self):
        p = pyaudio.PyAudio()
        stream_loopback = None
        stream_mic = None

        try:
            # 1. Discover WASAPI Host API
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            
            # Locate default speaker loopback
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers.get("isLoopbackDevice", False):
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
                else:
                    default_speakers = p.get_default_wasapi_loopback()

            loopback_rate = int(default_speakers["defaultSampleRate"])
            loopback_channels = int(default_speakers["maxInputChannels"])
            loopback_idx = default_speakers["index"]

            # Locate default microphone
            default_mic = p.get_default_input_device_info()
            mic_rate = int(default_mic["defaultSampleRate"])
            mic_channels = min(int(default_mic["maxInputChannels"]), 2)
            mic_idx = default_mic["index"]

            print(f"[DevListen Audio] Connected Loopback: {default_speakers['name']} ({loopback_rate}Hz)")
            print(f"[DevListen Audio] Connected Microphone: {default_mic['name']} ({mic_rate}Hz)")

            # Open WASAPI Loopback stream (non-exclusive / shared)
            stream_loopback = p.open(
                format=pyaudio.paInt16,
                channels=loopback_channels,
                rate=loopback_rate,
                input=True,
                input_device_index=loopback_idx,
                frames_per_buffer=1024
            )

            # Open Mic stream
            try:
                stream_mic = p.open(
                    format=pyaudio.paInt16,
                    channels=mic_channels,
                    rate=mic_rate,
                    input=True,
                    input_device_index=mic_idx,
                    frames_per_buffer=1024
                )
            except Exception as mic_err:
                print(f"[DevListen Audio] Warning: Mic open failed ({mic_err}). Running in Loopback-only mode.")
                stream_mic = None

            # Stream processing loop
            chunk_duration_sec = 0.05  # 50ms intervals
            while not self._stop_event.is_set():
                current_lb_level = 0.0
                current_mic_level = 0.0

                # Read Loopback
                try:
                    num_avail_lb = stream_loopback.get_read_available()
                    if num_avail_lb > 0:
                        raw_lb = stream_loopback.read(num_avail_lb, exception_on_overflow=False)
                        pcm_lb = np.frombuffer(raw_lb, dtype=np.int16)
                        if loopback_channels > 1:
                            pcm_lb = pcm_lb.reshape(-1, loopback_channels)[:, 0]  # Take left channel
                        # Resample to 16kHz if needed
                        pcm_lb_16k = self._resample(pcm_lb, loopback_rate, self.TARGET_SAMPLE_RATE)
                        
                        # RMS level for VU meter
                        if len(pcm_lb_16k) > 0:
                            rms_lb = float(np.sqrt(np.mean(pcm_lb_16k.astype(np.float32) ** 2)))
                            current_lb_level = min(1.0, max(0.0, rms_lb / 3500.0))

                        # Pass loopback audio when sound is active (digital silence gating)
                        if np.max(np.abs(pcm_lb_16k)) > 60:
                            if self.on_speech_chunk:
                                self.on_speech_chunk(pcm_lb_16k, "REMOTE")
                except Exception as lb_read_err:
                    raise lb_read_err

                # Read Mic
                if stream_mic:
                    try:
                        num_avail_mic = stream_mic.get_read_available()
                        if num_avail_mic > 0:
                            raw_mic = stream_mic.read(num_avail_mic, exception_on_overflow=False)
                            pcm_mic = np.frombuffer(raw_mic, dtype=np.int16)
                            if mic_channels > 1:
                                pcm_mic = pcm_mic.reshape(-1, mic_channels)[:, 0]
                            pcm_mic_16k = self._resample(pcm_mic, mic_rate, self.TARGET_SAMPLE_RATE)

                            if len(pcm_mic_16k) > 0:
                                rms_mic = float(np.sqrt(np.mean(pcm_mic_16k.astype(np.float32) ** 2)))
                                current_mic_level = min(1.0, max(0.0, rms_mic / 3500.0))

                            if self.vad_user.is_speech(pcm_mic_16k):
                                if self.on_speech_chunk:
                                    self.on_speech_chunk(pcm_mic_16k, "USER")
                    except Exception:
                        pass

                if self.on_levels_chunk:
                    self.on_levels_chunk(current_mic_level, current_lb_level)

                time.sleep(chunk_duration_sec)

        finally:
            if stream_loopback:
                try:
                    stream_loopback.stop_stream()
                    stream_loopback.close()
                except Exception:
                    pass
            if stream_mic:
                try:
                    stream_mic.stop_stream()
                    stream_mic.close()
                except Exception:
                    pass
            p.terminate()

    @staticmethod
    def _resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """High-fidelity polyphase sinc resampling preventing aliasing distortion."""
        if orig_sr == target_sr or len(samples) == 0:
            return samples
        try:
            import scipy.signal
            from math import gcd
            g = gcd(orig_sr, target_sr)
            up = target_sr // g
            down = orig_sr // g
            resampled = scipy.signal.resample_poly(samples.astype(np.float32), up, down)
            return np.clip(resampled, -32768, 32767).astype(np.int16)
        except Exception:
            # Fast fallback if scipy encounters non-standard array
            num_target_samples = int(len(samples) * target_sr / orig_sr)
            orig_indices = np.linspace(0, len(samples) - 1, len(samples))
            target_indices = np.linspace(0, len(samples) - 1, num_target_samples)
            resampled = np.interp(target_indices, orig_indices, samples)
            return resampled.astype(np.int16)
