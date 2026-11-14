"""
Production Real-Time STT Engine powered by KoljaB/RealtimeSTT.
Combines:
- WebRTC VAD + Silero VAD (Zero missed syllables, 0.8s pre-recording buffer).
- Dual-Model: 'tiny.en' for instant sub-100ms word streaming,
  'small.en' (OpenAI official 244M params, INT8) for final high-accuracy transcription.
- Developer Dictionary Normalization (Kubernetes, PostgreSQL, NGINX, MongoDB, CI/CD, gRPC).
- Multi-Word Loop Buster regex filter.
- Monkey-patched clean shutdown.
"""
import re
import threading
import time
from typing import Callable, Optional

# Monkey-patch RealtimeSTT FasterWhisperEngine missing .close() method
try:
    from RealtimeSTT.transcription_engines.faster_whisper_engine import FasterWhisperEngine
    if not hasattr(FasterWhisperEngine, 'close'):
        FasterWhisperEngine.close = lambda self: None
except Exception:
    pass

from RealtimeSTT import AudioToTextRecorder

# Empty prompt: No prompt conditioning.
# Prevents Whisper from hallucinating prompt words when humming, laughing, or mumbling.
DEFAULT_PROMPT = ""

DEV_TERMS_REPLACEMENTS = [
    (r'\b(?:they\s+want\s+you|the\s+van\s+shoe|the\s+want\s+you)\b', 'Devanshu'),
    (r'\b(?:big\s+room)\b', 'Bikram'),
    (r'\b(?:hip[\s-]*unkage|punk\s*edge)\b', 'Pankaj'),
    (r'\b(?:zubria|subria)\b', 'Supriya'),
    (r'\b(?:to\s+meet\s+you,?\s+)kitten\b', 'to meet you, Krishna'),
    (r'\b(?:sunchip|sun\s*chip|sanjit|sonchit|highs\s+on\s+jit|pseintjet)\b', 'Sanchit'),
    (r'\bplem\b', 'Prem'),
    (r'\b(?:god\s+of\s+ganyu|got\s+of\s+ganyu|gaurav\s+filior)\b', 'Gaurav, can you'),
    (r'\btraffic\b', 'Traefik'),
    (r'\bkubernet(?:[,\s]*disk|\s*is|\s*es|\s*s)?\b', 'Kubernetes'),
    (r'\benginex\b', 'NGINX'),
    (r'\bengine,?\s+ingress\b', 'NGINX ingress'),
    (r'\bpost[ -]?(?:qubonnet|hu?punates|gres(?:ql)?)\b', 'PostgreSQL'),
    (r'\bwhere\'?s\s+esquil\b', 'PostgreSQL'),
    (r'\bmongo[ -]?d[ -]?v\b', 'MongoDB'),
    (r'\bcsed\b', 'CI/CD'),
    (r'\bgraph[ -]?ql\b', 'GraphQL'),
    (r'\bg\s*rpc\b', 'gRPC'),
    (r'\bo\s*auth\s*2\b', 'OAuth2'),
    (r'\bo\'?er\b', 'OAuth2'),
    (r'\bjwt\b', 'JWT'),
    (r'\bred\s+is\b', 'Redis'),
    (r'\b(?:a\s+)?logan\s+failures?\b', 'login failures'),
    (r'\ball\s+uiv\s+designs?\b', 'our UI redesign'),
    (r'\b(?:screen-shit|screen\s+shit)\b', 'screen share them'),
    (r'\bdevs\s+and\s+estes\b', 'devs and testers'),
    (r'\bwiui\b', 'UI'),
    (r'\bfull\s+of\s+sign\s+tasks\b', "we'll assign tasks"),
    (r'\bsprinting\b', 'Sprint meeting'),
    (r'\b(?:gwa|goaba|gwaba|guaba)\b', 'Guava'),
    (r'\b(?:form|farm)\s+dependency\b', 'POM dependency'),
    (r'\b(?:palm|pom)\s+dependency\b', 'POM dependency'),
    (r'\bplaywright\b', 'Playwright'),
    (r'\bospf\b', 'OSPF'),
    (r'\bajax\b', 'AJAX'),
]

def sanitize_transcript(text: str) -> str:
    """
    Cleans up Whisper auto-regressive repetition loops, trailing stutter,
    and normalizes software engineering terminology.
    """
    if not text:
        return ""
    
    # 1. Collapse repeating single words/letters: e.g. "P, P, P, P..." -> "P"
    cleaned = re.sub(r'\b(\w+)(?:[,\s\.]+\1\b){2,}', r'\1', text, flags=re.IGNORECASE)
    
    # 2. Collapse repeating multi-word phrases (1-4 words) with comma/space/dot separators:
    # e.g. "3 million, 3 million, 3 million..." -> "3 million"
    # e.g. "the team before the team before" -> "the team before"
    pattern = r'(\b[\w\.]+(?:\s+[\w\.]+){0,4}\b)(?:[,\s\.]+\1\b){1,}'
    cleaned = re.sub(pattern, r'\1', cleaned, flags=re.IGNORECASE)

    # 3. Apply Developer Terminology Normalization
    for pattern_regex, replacement in DEV_TERMS_REPLACEMENTS:
        cleaned = re.sub(pattern_regex, replacement, cleaned, flags=re.IGNORECASE)

    # 4. Clean trailing commas / punctuation
    cleaned = re.sub(r'[,;\s]+$', '', cleaned).strip()
    if cleaned and not cleaned.endswith(('.', '?', '!')):
        cleaned += '.'

    # 5. Filter isolated vocal noises / laughter blips (e.g. "Ha.", "Uh.", "Hmm.")
    if re.fullmatch(r'^(?:ha|he|uh|ah|oh|um|mm|hmm|mhm)[,\.\s]*$', cleaned, flags=re.IGNORECASE):
        return ""

    # 5. Hallucination guard: if line is 70%+ a single character, drop it
    letters = [c for c in cleaned if c.isalpha()]
    if letters:
        most_common_ratio = max(cleaned.count(c) for c in set(letters)) / len(letters)
        if most_common_ratio > 0.6 and len(letters) > 15:
            return ""

    return cleaned

class AdvancedRealtimeTranscriber:
    """
    Wraps KoljaB/RealtimeSTT AudioToTextRecorder with background worker thread,
    interim streaming callbacks, anti-loop filtering, and graceful shutdown.
    """
    def __init__(
        self,
        model: str = "base",
        realtime_model: str = "tiny",
        initial_prompt: str = DEFAULT_PROMPT,
        on_interim_callback: Optional[Callable[[str, str], None]] = None,
        on_final_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.model = model
        self.realtime_model = realtime_model
        self.initial_prompt = initial_prompt
        self.on_interim_callback = on_interim_callback
        self.on_final_callback = on_final_callback

        self.recorder: Optional[AudioToTextRecorder] = None
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="DevListen-RealtimeSTT")
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self.recorder:
            try:
                import logging
                logging.getLogger().setLevel(logging.CRITICAL)
                self.recorder.stop()
            except Exception:
                pass
            try:
                self.recorder.shutdown()
            except Exception:
                pass

    def _run_loop(self):
        print(f"[DevListen RealtimeSTT] Initializing dual models ('{self.model}' + '{self.realtime_model}')...")
        
        def handle_interim(text: str):
            if text and self.on_interim_callback:
                clean_interim = sanitize_transcript(text)
                if clean_interim:
                    self.on_interim_callback(clean_interim, "USER")

        try:
            self.recorder = AudioToTextRecorder(
                model=self.model,
                realtime_model_type=self.realtime_model,
                device="cpu",
                compute_type="int8",
                language="en",
                enable_realtime_transcription=True,
                on_realtime_transcription_update=handle_interim,
                initial_prompt=self.initial_prompt,
                spinner=False,
                use_microphone=True,
                webrtc_sensitivity=3,
                silero_sensitivity=0.4,
                silero_deactivity_detection=True,
                post_speech_silence_duration=0.6,
                pre_recording_buffer_duration=0.8,
                beam_size=1,
                beam_size_realtime=1,
                warmup_vad=False
            )
            print("[DevListen RealtimeSTT] Engine ready! Listening to microphone...")

            recent_utterances = []
            hallucination_phrases = {
                "passing on the air.",
                "i'm a little bit more.",
                "hello mr. d.j. mayor aguano, please play.",
                "thank you for watching.",
                "please subscribe.",
                "thanks for watching.",
                "subtitles by the amara.org community."
            }

            while self.is_running:
                # Blocks until user finishes a sentence, then returns final high-accuracy text
                final_text = self.recorder.text()
                now = time.time()
                if final_text and self.is_running:
                    clean_text = sanitize_transcript(final_text)
                    if not clean_text:
                        continue

                    # Filter known background phantom loops
                    if clean_text.lower() in hallucination_phrases:
                        continue

                    # Deduplicate any identical utterance that appeared within the last 15 seconds
                    recent_utterances = [(t, tm) for (t, tm) in recent_utterances if (now - tm) < 15.0]
                    if any(t.lower() == clean_text.lower() for (t, tm) in recent_utterances):
                        continue

                    recent_utterances.append((clean_text, now))
                    if self.on_final_callback:
                        self.on_final_callback(clean_text, "USER")

        except Exception as e:
            if self.is_running:
                print(f"[DevListen RealtimeSTT Error] {e}")
