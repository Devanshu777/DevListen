"""
Autonomous Commitment & Action Item Extractor for DevListen.
Parses conversational utterances in real time to capture:
- Verbal commitments and promises ("I will send the PR", "Alex is checking the logs")
- Explicit task assignments ("Let's assign tasks to devs and testers")
- Due dates and conditions ("by end of day", "before the release")
Registers tasks into the local SQLite database and emits live updates.
"""
import re
import uuid
import datetime
from typing import Dict, Any, Optional, List
from vault.database import VaultDatabase

class CommitmentExtractor:
    """
    Extracts action items, accountability promises, and assignments
    from natural language conversational turns.
    """
    def __init__(self, db: VaultDatabase):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensures the action_items table exists in the vault."""
        with self.db.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS action_items (
                id TEXT PRIMARY KEY,
                meeting_uuid TEXT,
                assignee TEXT NOT NULL,
                task_description TEXT NOT NULL,
                due_hint TEXT,
                completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (meeting_uuid) REFERENCES meetings(uuid)
            )
            """)
            conn.commit()

    def analyze_utterance(self, text: str, speaker: str, meeting_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Parses text for commitments. Returns structured dict if an action item is detected.
        """
        if not text or len(text.strip()) < 12:
            return None

        clean = text.strip()

        # Sentence terminator: period followed by space or end of line, or ! ?
        term = r'(?:\.(?:\s|$)|[!?]|\Z)'

        # Pattern 1: Self-commitment ("I will / I'll / I am going to / I'll make sure to")
        m_self = re.search(
            r'\b(?:i\s+will|i\'?ll|i\'?m\s+going\s+to|i\s+can|i\'?ll\s+make\s+sure\s+to|let\s+me)\s+(?P<task>(?:update|send|check|verify|fix|create|deploy|investigate|test|review|assign|write|add|remove|open|push|merge|screen[\s-]share|tweak)\b.*?)' + term,
            clean,
            re.IGNORECASE
        )
        if m_self:
            task_raw = m_self.group("task").strip()
            task_clean = self._clean_task_text(task_raw)
            if task_clean:
                return self._record_action(meeting_uuid, speaker, task_clean)

        # Pattern 2: Third-party assignment / commitment ("Alex will / Sarah is going to / We need to assign")
        m_assign = re.search(
            r'\b(?P<who>[A-Z][a-z]+|speaker\s+[A-D]|we|team)\s+(?:will|is\s+going\s+to|committed\s+to|should\s+take\s+care\s+of)\s+(?P<task>(?:update|send|check|verify|fix|create|deploy|investigate|test|review|assign|write|open|push|merge)\b.*?)' + term,
            clean,
            re.IGNORECASE
        )
        if m_assign:
            who = m_assign.group("who").strip()
            task_raw = m_assign.group("task").strip()
            task_clean = self._clean_task_text(task_raw)
            if task_clean:
                assignee = who if who.lower() not in ("we", "team") else "Team"
                return self._record_action(meeting_uuid, assignee, task_clean)

        # Pattern 3: Imperative team action ("We need to update / We must verify / Let's task that")
        m_team = re.search(
            r'\b(?:we\s+need\s+to|we\s+have\s+to|we\s+must|let\'?s|let\s+us)\s+(?P<task>(?:update|deploy|verify|fix|investigate|refactor|test|check|assign|split)\b.*?)' + term,
            clean,
            re.IGNORECASE
        )
        if m_team:
            task_raw = m_team.group("task").strip()
            task_clean = self._clean_task_text(task_raw)
            if task_clean:
                return self._record_action(meeting_uuid, "Team", task_clean)

        return None

    def _clean_task_text(self, raw: str) -> Optional[str]:
        # Strip trailing conversational fluff
        cleaned = re.sub(r'\b(as\s+well|too|today|tomorrow|soon|if\s+possible|you\s+know|i\s+think)\b', '', raw, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,;:-')
        # Remove trailing dangling prepositions
        cleaned = re.sub(r'\s+\b(by|to|at|for|in|on|with|from)\b\s*$', '', cleaned, flags=re.IGNORECASE).strip()
        if len(cleaned.split()) < 3:
            return None
        return cleaned[:120].capitalize()

    def _record_action(self, meeting_uuid: str, assignee: str, task: str) -> Dict[str, Any]:
        item_id = str(uuid.uuid4())
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO action_items (id, meeting_uuid, assignee, task_description) VALUES (?, ?, ?, ?)",
                (item_id, meeting_uuid, assignee, task)
            )
            conn.commit()

        return {
            "id": item_id,
            "meeting_uuid": meeting_uuid,
            "assignee": assignee,
            "task": task,
            "completed": False,
            "timestamp": datetime.datetime.now().strftime("%H:%M")
        }

    def get_actions_for_meeting(self, meeting_uuid: str) -> List[Dict[str, Any]]:
        """Retrieves all tracked commitments for a given meeting."""
        with self.db.get_connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT id, assignee, task_description, completed, created_at FROM action_items WHERE meeting_uuid = ? ORDER BY rowid ASC",
                (meeting_uuid,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "assignee": r["assignee"],
                    "task": r["task_description"],
                    "completed": bool(r["completed"]),
                    "created_at": r["created_at"]
                }
                for r in rows
            ]
