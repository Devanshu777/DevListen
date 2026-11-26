"""
100% Offline Local Speech-to-Text Transcriber using faster-whisper.
Runs INT8 quantized models on CPU with zero network calls and near-zero latency.
Transcribes speech segments accumulated from the VAD-gated audio engine.
Hardened with queue-lag drain protection to prevent latency accumulation.
"""
import re
import time
import queue
import threading
import numpy as np
from typing import Callable, Optional, List, Tuple
from faster_whisper import WhisperModel
from core.dev_terms import DEV_TERMS_REPLACEMENTS

# Empty prompt: No prompt conditioning.
# Prevents Whisper from hallucinating prompt words when humming, laughing, or mumbling.
DEFAULT_TECHNICAL_PROMPT = ""

YOUTUBE_HALLUCINATIONS = [
    r'\bthank you for watching[,\.]?',
    r'\bthank you for your time[,\.]?',
    r'\bthanks for watching[,\.]?',
    r'\bplease subscribe[,\.]?',
    r'\blike and subscribe[,\.]?',
    r'\band that\'?s the end of the video[,\.]?',
    r'\bsee you in the next video[,\.]?',
    r'\band that\'?s the end of the session[,\.]?',
    r'\bthank you[\s\.\,]+thank[\s\.\,]*',
]

def clean_repetitions(text: str) -> str:
    """Removes single phrase repeats, alternating cycles, and n-gram repeat loops."""
    if not text:
        return ""
    # 1. Multi-word or phrase repetition loop buster (with punctuation)
    cleaned = re.sub(r'(\b.+?\b)(?:[\s,\.\?\!\-]+\1){2,}', r'\1', text, flags=re.IGNORECASE).strip()

    # 2. Alternating clause cycle buster: (Clause A. Clause B.) (Clause A. Clause B.)
    clauses = [c.strip() for c in re.split(r'(?<=[.?!])\s+', cleaned) if c.strip()]
    if len(clauses) >= 4:
        def norm(s): return re.sub(r'[^\w]', '', s.lower())
        # Check period 2: clauses 0,1 == clauses 2,3
        if norm(clauses[0]) == norm(clauses[2]) and norm(clauses[1]) == norm(clauses[3]):
            cleaned = " ".join(clauses[:2])
        # Check period 1: clauses 0 == clauses 1 == clauses 2
        elif len(clauses) >= 3 and norm(clauses[0]) == norm(clauses[1]):
            cleaned = clauses[0]

    # 3. Detect and truncate repeating phrases of 5+ words that recur in the text
    words = cleaned.split()
    if len(words) >= 10:
        norm_words = [re.sub(r'[^\w]', '', w.lower()) for w in words]
        for n in range(min(12, len(words) // 2), 4, -1):
            found = False
            for i in range(len(words) - n):
                sub = norm_words[i : i + n]
                if not all(sub):
                    continue
                for j in range(i + n, len(words) - n + 1):
                    if norm_words[j : j + n] == sub:
                        # Backtrack j to the preceding sentence boundary
                        cutoff = j
                        while cutoff > 0 and not words[cutoff - 1].endswith(('.', '?', '!')):
                            cutoff -= 1
                        if cutoff == 0:
                            cutoff = j
                        words = words[:cutoff]
                        cleaned = " ".join(words).rstrip(' ,;:-')
                        if cleaned and cleaned[-1] not in '.?!':
                            cleaned += '.'
                        found = True
                        break
                if found:
                    break
            if found:
                break

    return cleaned

def split_segment_into_clauses(seg) -> List[Tuple[float, float, str]]:
    """Splits a Whisper segment into individual speaker clauses based on word pauses and punctuation."""
    if not hasattr(seg, 'words') or not seg.words:
        return [(seg.start, seg.end, seg.text.strip())]

    clauses = []
    current_words = []
    current_start = seg.words[0].start

    for w in seg.words:
        if current_words:
            prev = current_words[-1]
            gap = w.start - prev.end
            prev_word = prev.word.strip()
            w_clean = w.word.lower().strip()

            # Conversational turn boundaries:
            # 1. Natural inter-speaker pause >= 0.75s
            # 2. Question / exclamation followed by conversational gap >= 0.35s
            # 3. Interjection starters ("Wait", "Actually", "No") after sentence boundary with gap >= 0.40s
            is_turn_boundary = (
                gap >= 0.75 or
                (prev_word.endswith(('?', '!')) and gap >= 0.35) or
                (prev_word.endswith(('.', '?', '!')) and gap >= 0.40 and w_clean in ('wait', 'actually', 'no', 'hold on'))
            )

            if is_turn_boundary:
                text_part = " ".join([cw.word for cw in current_words]).strip()
                if text_part:
                    clauses.append((current_start, prev.end, text_part))
                current_words = [w]
                current_start = w.start
                continue

        current_words.append(w)

    if current_words:
        text_part = " ".join([cw.word for cw in current_words]).strip()
        if text_part:
            clauses.append((current_start, current_words[-1].end, text_part))

    return clauses

def clean_clause_text(text: str) -> str:
    """Cleans repetition cycles, echoes, and developer terms on a single speech clause."""
    if not text:
        return ""
    text = clean_repetitions(text)
    text = re.sub(r'\b(?:a\s+)?technical\s+software(?:\s+engineering)?(?:\s+discussion)?\b[,\.]?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\buse proper punctuation\b[,\.]?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:(?:GitLab|Semgrep|DAST|fuzzing|acquisition[s]?)[,\.\s]+){2,}(?:GitLab|Semgrep|DAST|fuzzing|acquisition[s]?)?[,\.]?', '', text, flags=re.IGNORECASE).strip()
    for yt_pat in YOUTUBE_HALLUCINATIONS:
        text = re.sub(yt_pat, '', text, flags=re.IGNORECASE).strip()
    for pat, rep in DEV_TERMS_REPLACEMENTS:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    # Filter isolated Whisper hallucination artifacts on silence / breathing
    clean_lower = re.sub(r'[^\w\s]', '', text).strip().lower()
    if clean_lower in ('you', 'thank you', 'thanks', 'bye', 'so', 'the', 'a', 'an', 'it', 'its'):
        return ""

    if not re.search(r'[a-zA-Z]{2,}', text) or re.fullmatch(r'[\s\.\,\?\!\:\;\-]+', text):
        return ""
    return text.strip()

class LocalTranscriber:
    """
    Asynchronous worker that receives 16kHz PCM speech chunks and transcribes
    them locally on CPU using faster-whisper CTranslate2 INT8 engine.
    """
    def __init__(
        self,
        model_size: str = "base",
        initial_prompt: str = DEFAULT_TECHNICAL_PROMPT,
        on_transcript_callback: Optional[Callable[[str, str, np.ndarray], None]] = None
    ):
        self.model_size = model_size
        self.initial_prompt = initial_prompt
        self.on_transcript_callback = on_transcript_callback
        self.model: Optional[WhisperModel] = None

        self._queue = queue.Queue(maxsize=50)
        self.is_running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Buffers for speech accumulation
        self._user_buffer = []
        self._remote_buffer = []
        self._last_user_speech_time = 0
        self._last_remote_speech_time = 0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._worker_thread = threading.Thread(
            target=self._transcription_worker,
            daemon=True,
            name="DevListen-LocalTranscriber"
        )
        self._worker_thread.start()

    def stop(self):
        self.is_running = False
        self._queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def feed_chunk(self, pcm_chunk_16k: np.ndarray, source: str):
        """
        Feeds raw 16kHz int16 PCM chunk into the accumulator.
        Source: 'USER' or 'REMOTE'.
        """
        now = time.time()
        if source == "USER":
            self._user_buffer.append(pcm_chunk_16k)
            self._last_user_speech_time = now
        else:
            self._remote_buffer.append(pcm_chunk_16k)
            self._last_remote_speech_time = now

        # Flush if ~1.25s of speech accumulated (20,000 samples @ 16kHz)
        self._check_and_flush(source)

    def _check_and_flush(self, source: str):
        buf = self._user_buffer if source == "USER" else self._remote_buffer
        total_samples = sum(len(c) for c in buf)

        # Accumulate speech for ~3.5s (56,000 samples @ 16kHz) for high-accuracy sentence context during continuous fast speech
        if total_samples >= 56000:
            self.flush(source, is_silence_flush=False)

    def flush(self, source: str, is_silence_flush: bool = True):
        """
        Dispatches accumulated speech buffer to the transcription worker with acoustic boundary protection.
        - On silence flush: speaker finished speaking; buffer is dispatched and fully cleared.
        - On mid-speech flush: retains trailing 400ms overlap so fast words at the seam are NEVER cut in half.
        """
        buf = self._user_buffer if source == "USER" else self._remote_buffer
        if not buf:
            return

        combined = np.concatenate(buf)
        overlap_samples = 6400  # 400ms overlap at 16kHz

        if is_silence_flush or len(combined) <= overlap_samples * 2:
            buf.clear()
            self._queue.put((combined, source))
        else:
            overlap_pcm = combined[-overlap_samples:]
            buf.clear()
            buf.append(overlap_pcm)
            self._queue.put((combined, source))

    def _transcription_worker(self):
        """Loads local model and processes transcription queue with zero backlog."""
        print(f"[DevListen STT] Loading local model '{self.model_size}' (INT8 CPU, 4 threads)...")
        # Load whisper model with int8 quantization on CPU with 4 threads
        self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8", cpu_threads=4)
        print("[DevListen STT] Local model loaded and ready! 100% Offline.")

        while self.is_running:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                # Flush on conversational silence (0.35s)
                now = time.time()
                if self._user_buffer and (now - self._last_user_speech_time > 0.35):
                    self.flush("USER", is_silence_flush=True)
                if self._remote_buffer and (now - self._last_remote_speech_time > 0.35):
                    self.flush("REMOTE", is_silence_flush=True)
                continue

            if item is None:
                break

            pcm_data, source = item

            # Backlog drain protection: If queue is backed up, combine pending items to catch up to real-time
            drain_chunks = [pcm_data]
            while not self._queue.empty() and len(drain_chunks) < 3:
                try:
                    next_item = self._queue.get_nowait()
                    if next_item is None:
                        break
                    drain_chunks.append(next_item[0])
                    self._queue.task_done()
                except queue.Empty:
                    break

            if len(drain_chunks) > 1:
                pcm_data = np.concatenate(drain_chunks)

            try:
                # Convert int16 to normalized float32 [-1.0, 1.0]
                audio_f32 = pcm_data.astype(np.float32) / 32768.0

                # High-speed greedy inference: vad_filter=False ensures fast speech and unstressed syllables are never clipped
                segments, info = self.model.transcribe(
                    audio_f32,
                    language="en",
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    compression_ratio_threshold=2.4,
                    condition_on_previous_text=False,
                    initial_prompt=self.initial_prompt,
                    word_timestamps=False,
                    vad_filter=False
                )

                # Process transcribed segments directly with the full acoustic context
                for seg in segments:
                    clean_text = clean_clause_text(seg.text)
                    if not clean_text or len(clean_text) < 2:
                        continue

                    # Pass the full acoustic PCM buffer to the diarizer for high-confidence CAM++ 512-d embeddings
                    if self.on_transcript_callback:
                        self.on_transcript_callback(clean_text, source, pcm_data)

            except Exception as e:
                print(f"[DevListen STT] Transcription error: {e}")
            finally:
                self._queue.task_done()
