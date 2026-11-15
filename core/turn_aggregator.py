"""
Conversational Turn Aggregator for DevListen.
Aggregates fragmented real-time speech chunks into cohesive, whole-thought
paragraphs and statements (like ChatGPT / Gemini voice mode).

Emits:
- on_turn_update(current_paragraph, speaker): Live update as the speaker speaks.
- on_turn_finalize(full_statement, speaker): Finalized complete statement when
  the speaker finishes their thought (conversational pause) or speaker changes.
"""
import re
import time
import threading
from typing import Callable, Optional, List

def merge_turn_segments(existing: str, new_chunk: str) -> str:
    """
    Intelligently joins real-time transcribed speech segments:
    - Eliminates boundary word overlap (e.g. 'GitLab 14' + 'GitLab 14 launch' -> 'GitLab 14 launch').
    - Manages capitalization and punctuation between sentences.
    """
    clean_new = new_chunk.strip()
    if not clean_new:
        return existing
    if not existing:
        # Capitalize first letter
        return clean_new[0].upper() + clean_new[1:] if len(clean_new) > 1 else clean_new.upper()

    clean_existing = existing.strip()

    # 1. Overlap detection (up to 4 words)
    ex_words = clean_existing.split()
    new_words = clean_new.split()

    overlap_len = 0
    max_check = min(5, len(ex_words), len(new_words))
    for k in range(max_check, 0, -1):
        tail = [re.sub(r'[^\w]', '', w.lower()) for w in ex_words[-k:]]
        head = [re.sub(r'[^\w]', '', w.lower()) for w in new_words[:k]]
        if tail == head and all(tail):
            # If single word overlap, require at least 3 letters to prevent false match on short single letters
            if k == 1 and len(tail[0]) < 3:
                continue
            overlap_len = k
            break

    if overlap_len > 0:
        clean_new = " ".join(new_words[overlap_len:])
        if not clean_new:
            return clean_existing
        return f"{clean_existing} {clean_new}"

    # 2. Punctuation & sentence casing
    trailing_word = ex_words[-1].lower().rstrip('.,?!:;')
    if trailing_word in ('or', 'and', 'but', 'with', 'that', 'of', 'to', 'in', 'as', 'is', 'a', 'the', 'some', 'kind', 'like', 'for'):
        return f"{clean_existing} {clean_new}"

    if clean_existing.endswith(('.', '?', '!', ';')):
        clean_new = clean_new[0].upper() + clean_new[1:] if len(clean_new) > 1 else clean_new.upper()
        return f"{clean_existing} {clean_new}"
    elif clean_existing.endswith((',', '...')):
        return f"{clean_existing} {clean_new}"
    else:
        # Mid-sentence continuation across speech buffers: preserve flow without artificial periods
        return f"{clean_existing} {clean_new}"

class ConversationalTurnAggregator:
    """
    Manages conversational speech turns, accumulating continuous utterances into
    full statements/paragraphs until a turn boundary is detected.
    """
    def __init__(
        self,
        silence_timeout: float = 8.5,
        max_paragraph_words: int = 130,
        on_turn_update: Optional[Callable[[str, str], None]] = None,
        on_turn_finalize: Optional[Callable[[str, str], None]] = None
    ):
        self.silence_timeout = silence_timeout
        self.max_paragraph_words = max_paragraph_words
        self.on_turn_update = on_turn_update
        self.on_turn_finalize = on_turn_finalize

        self.current_speaker: Optional[str] = None
        self.current_text: str = ""
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def feed(self, chunk_text: str, speaker: str):
        """Feeds a new transcribed speech fragment into the turn accumulator."""
        text = chunk_text.strip()
        if not text:
            return

        with self._lock:
            self._extended_wait = False
            # Cancel any pending silence finalization timer
            self._cancel_timer()

            # If speaker switched (e.g. Speaker A -> Speaker B), finalize previous speaker immediately
            if self.current_speaker is not None and speaker != self.current_speaker:
                self._finalize_locked()

            # Accumulate into current speaker's statement
            self.current_speaker = speaker
            self.current_text = merge_turn_segments(self.current_text, text)
            full_text = self.current_text
            spk = self.current_speaker

            # If current paragraph reaches natural reading length (~130 words) and ends with a sentence, finalize
            if len(full_text.split()) >= self.max_paragraph_words and full_text.endswith(('.', '?', '!')):
                self._finalize_locked()
                return

            # If current text ends with a question '?', use a shorter timeout (2.2s)
            # because questions naturally invite another speaker to answer
            effective_timeout = 2.2 if text.endswith('?') else self.silence_timeout
            self._timer = threading.Timer(effective_timeout, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

        # Emit live update so HUD displays statement in real-time as words arrive
        if self.on_turn_update:
            try:
                self.on_turn_update(full_text, spk)
            except Exception as e:
                print(f"[DevListen Aggregator] Update callback error: {e}")

    def _on_timeout(self):
        """Called when silence timeout expires (speaker paused and concluded thought)."""
        with self._lock:
            # Check if speaker paused on an unfinished thought / dangling conjunction
            text = self.current_text.strip()
            words = text.split()
            if words:
                last_word = re.sub(r'[^\w]', '', words[-1].lower())
                # If speaker paused on a conjunction or trailing ellipsis, allow an extra extension
                if (last_word in ('or', 'and', 'but', 'because', 'so', 'with', 'that', 'um', 'uh', 'like', 'for', 'if', 'when', 'to') 
                    or text.endswith('...')) and not getattr(self, '_extended_wait', False):
                    self._extended_wait = True
                    self._timer = threading.Timer(2.0, self._on_timeout)
                    self._timer.daemon = True
                    self._timer.start()
                    return

            self._extended_wait = False
            self._finalize_locked()

    def _finalize_locked(self):
        if not self.current_text or not self.current_speaker:
            return

        statement = self.current_text.strip()
        speaker = self.current_speaker

        # Ensure trailing sentence punctuation
        if statement and statement[-1] not in ('.', '?', '!'):
            statement += "."

        # Clear state
        self.current_text = ""
        self.current_speaker = None
        self._cancel_timer()

        # Emit finalized paragraph
        if self.on_turn_finalize:
            try:
                self.on_turn_finalize(statement, speaker)
            except Exception as e:
                print(f"[DevListen Aggregator] Finalize callback error: {e}")

    def _cancel_timer(self):
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
            self._timer = None

    def flush(self):
        """Forces immediate finalization of any pending statement."""
        with self._lock:
            self._finalize_locked()
