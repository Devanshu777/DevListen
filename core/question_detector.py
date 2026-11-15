"""
Proactive Question & Inquiry Detector for DevListen (Brick 6).
Detects live conversational inquiries during calls (e.g. from Remote Attendees)
and triggers zero-click context flash cards on the Stealth HUD.
"""
import re
from typing import Optional, Tuple

QUESTION_PREFIXES = (
    "what", "why", "how", "who", "when", "which", "where",
    "did we", "do we", "are we", "is there", "can we",
    "should we", "will we", "have we", "could we", "would we",
    "tell me about", "update on", "status on", "status of", "what's the update",
    "any idea about", "do you know", "why did"
)

QUESTION_PATTERNS = [
    r'\b(?:what|why|how|who|which)\b.*\?',
    r'\b(?:did|do|are|is|can|should|will|have)\s+we\b.*\?',
    r'\b(?:status|update)\s+(?:on|of|about)\b',
    r'\b(?:why\s+did\s+(?:the\s+)?(?:architect|team|we))\b',
    r'\b(?:what\s+did\s+(?:the\s+)?(?:architect|team|we)\s+decide)\b',
    r'\b(?:what(?:\'s|\s+is)\s+(?:the|our)\s+(?:plan|status|decision|strategy))\b',
    r'\b(?:why\s+(?:not|aren\'?t\s+we\s+using))\b'
]

class QuestionDetector:
    """
    Analyzes live utterances in < 1ms to detect questions and information requests.
    """
    @staticmethod
    def is_question(text: str) -> bool:
        if not text or len(text.strip()) < 8:
            return False

        clean = text.strip().lower()

        # Direct question mark check
        if clean.endswith('?'):
            return True

        # Check for question starter prefixes
        for prefix in QUESTION_PREFIXES:
            if clean.startswith(prefix + " ") or clean.startswith(prefix + "'"):
                return True

        # Check regex patterns
        for pat in QUESTION_PATTERNS:
            if re.search(pat, clean):
                return True

        return False
