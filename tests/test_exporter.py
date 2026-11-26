"""
Isolated tests for MeetingExporter (including sqlite3.Row decision export).
"""
import uuid
from pathlib import Path

from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.commitment_extractor import CommitmentExtractor
from export.meeting_exporter import MeetingExporter


def test_export_latest_meeting_with_decisions_and_actions(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("os.path.expanduser", lambda _: str(tmp_path))

    db = VaultDatabase(db_path=str(tmp_path / "export_test.db"))
    graph = TemporalDecisionGraph(db)
    ce = CommitmentExtractor(db)

    m_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
            (m_uuid, "Architecture Review", "Teams"),
        )
        conn.commit()

    d1 = graph.record_decision(m_uuid, "Redis", "Use Redis for caching", proposed_by="Alex", status="ACTIVE")
    graph.record_decision(
        m_uuid,
        "Redis",
        "Hold off on Redis until Schema v2",
        proposed_by="Team",
        status="ACTIVE",
        supersedes_decision_id=d1,
    )
    ce.analyze_utterance("I will update the ADR documentation today.", "YOU", m_uuid)

    out_path = MeetingExporter.export_latest_meeting(db)
    assert out_path
    content = Path(out_path).read_text(encoding="utf-8")
    assert "Architecture Review" in content
    assert "[SUPERSEDED]" in content
    assert "[ACTIVE]" in content
    assert "Hold off on Redis until Schema v2" in content
    assert "Update the adr documentation" in content


def test_export_empty_database_returns_empty_string(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("os.path.expanduser", lambda _: str(tmp_path))
    db = VaultDatabase(db_path=str(tmp_path / "empty.db"))
    assert MeetingExporter.export_latest_meeting(db) == ""
