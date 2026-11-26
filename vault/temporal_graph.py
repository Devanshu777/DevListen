"""
Bi-Temporal Knowledge Graph & Decision Engine.
Handles inserting decisions, superseding outdated decisions, and resolving
context with chronological state decay so outdated decisions are never returned as current.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from vault.database import VaultDatabase

class TemporalDecisionGraph:
    """
    Manages project entities and state-evolving technical decisions.
    """
    def __init__(self, db: VaultDatabase):
        self.db = db

    def record_decision(
        self,
        meeting_uuid: str,
        entity_name: str,
        summary: str,
        proposed_by: str = "Unknown",
        agreed_by: str = "Team",
        status: str = "ACTIVE",
        supersedes_decision_id: Optional[str] = None
    ) -> str:
        """
        Records a new decision. If it supersedes a prior decision, marks the previous
        one as SUPERSEDED with an exact timestamp link.
        """
        decision_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        with self.db.get_connection(read_only=False) as conn:
            # 1. Ensure entity exists
            conn.execute(
                """
                INSERT INTO entities (name, last_updated)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET last_updated=excluded.last_updated
                """,
                (entity_name, now)
            )

            # 2. If superseding, invalidate previous decision
            if supersedes_decision_id:
                conn.execute(
                    """
                    UPDATE decisions
                    SET status = 'SUPERSEDED', superseded_at = ?, superseded_by_id = ?
                    WHERE decision_id = ?
                    """,
                    (now, decision_id, supersedes_decision_id)
                )

            # 3. Insert new decision
            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, meeting_uuid, entity_name, summary,
                    proposed_by, agreed_by, status, effective_from
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, meeting_uuid, entity_name, summary, proposed_by, agreed_by, status, now)
            )
            conn.commit()

        return decision_id

    def get_entity_context(self, entity_name: str) -> Dict[str, Any]:
        """
        Retrieves the complete temporal history of an entity.
        Returns the latest decision (ACTIVE or REJECTED) alongside superseded history.
        """
        with self.db.get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT decision_id, summary, proposed_by, agreed_by, status,
                       effective_from, superseded_at
                FROM decisions
                WHERE entity_name = ? COLLATE NOCASE
                ORDER BY effective_from DESC
                """,
                (entity_name,)
            )
            rows = [dict(r) for r in cursor.fetchall()]

        latest = rows[0] if rows else None
        
        # Filter historical decisions to only include meaningfully different prior decisions
        history = []
        if latest:
            seen_summaries = {latest["summary"].strip().lower()}
            for r in rows[1:]:
                sm = r["summary"].strip().lower()
                if sm not in seen_summaries:
                    history.append(r)
                    seen_summaries.add(sm)
        else:
            history = rows[1:]

        return {
            "entity": entity_name,
            "current_decision": latest,
            "historical_decisions": history
        }

    def search_recent_decisions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Pre-fetches recent active decisions for the stealth HUD hot-cache."""
        with self.db.get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT d.entity_name, d.summary, d.status, d.effective_from, m.title as meeting_title
                FROM decisions d
                JOIN meetings m ON d.meeting_uuid = m.uuid
                WHERE d.status = 'ACTIVE'
                ORDER BY d.effective_from DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]
