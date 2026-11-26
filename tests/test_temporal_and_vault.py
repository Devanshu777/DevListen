"""
Isolated unit and integration tests for VaultDatabase, TemporalDecisionGraph,
format_context_html, and VaultCrypto.
"""
import sys
import uuid
import pytest
from pathlib import Path

from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.context_formatter import format_context_html
from vault.crypto import VaultCrypto


def _create_meeting(db: VaultDatabase, title: str = "Arch Sync", platform: str = "Local") -> str:
    m_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
            (m_uuid, title, platform),
        )
        conn.commit()
    return m_uuid


def test_temporal_supersession_and_context(tmp_path: Path):
    db = VaultDatabase(db_path=str(tmp_path / "vault.db"))
    graph = TemporalDecisionGraph(db)
    m1 = _create_meeting(db, "Architecture Sync", "Zoom")
    m2 = _create_meeting(db, "Weekly Standup", "Teams")

    d1_id = graph.record_decision(
        meeting_uuid=m1,
        entity_name="GraphQL Caching",
        summary="Use Redis for response caching",
        proposed_by="Lead Architect",
        agreed_by="Alex",
        status="ACTIVE",
    )
    d2_id = graph.record_decision(
        meeting_uuid=m2,
        entity_name="GraphQL Caching",
        summary="Hold off on Redis until Schema v2 lands",
        proposed_by="Lead Architect",
        agreed_by="Team",
        status="ACTIVE",
        supersedes_decision_id=d1_id,
    )

    ctx = graph.get_entity_context("GraphQL Caching")
    assert ctx["entity"] == "GraphQL Caching"
    assert ctx["current_decision"]["decision_id"] == d2_id
    assert ctx["current_decision"]["status"] == "ACTIVE"
    assert len(ctx["historical_decisions"]) == 1
    assert ctx["historical_decisions"][0]["decision_id"] == d1_id
    assert ctx["historical_decisions"][0]["status"] == "SUPERSEDED"

    # Verify HTML formatter renders both current truth and superseded history
    rendered = format_context_html(ctx)
    assert "CURRENT TRUTH [ACTIVE]" in rendered
    assert "Hold off on Redis until Schema v2 lands" in rendered
    assert "[SUPERSEDED]" in rendered
    assert "Use Redis for response caching" in rendered


def test_repeated_identical_decision_deduplicated_in_history(tmp_path: Path):
    db = VaultDatabase(db_path=str(tmp_path / "vault.db"))
    graph = TemporalDecisionGraph(db)
    m1 = _create_meeting(db)

    d1 = graph.record_decision(m1, "PostgreSQL", "Use PostgreSQL 16", status="ACTIVE")
    graph.record_decision(m1, "PostgreSQL", "Use PostgreSQL 16", status="ACTIVE", supersedes_decision_id=d1)

    ctx = graph.get_entity_context("PostgreSQL")
    assert ctx["current_decision"]["summary"] == "Use PostgreSQL 16"
    assert ctx["historical_decisions"] == []


def test_format_context_html_empty_and_escaped():
    rendered = format_context_html({"entity": "<script>alert(1)</script>"})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "No recorded decisions found" in rendered


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only available on win32")
def test_vault_crypto_roundtrip(tmp_path: Path, monkeypatch):
    # Reset cached master key and point LOCALAPPDATA to tmp_path
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    VaultCrypto._master_key = None

    secret = "Confidential architecture decision: migrate to OAuth2."
    encrypted = VaultCrypto.encrypt_data(secret)
    assert encrypted != secret.encode("utf-8")
    assert VaultCrypto.decrypt_data(encrypted) == secret
    VaultCrypto._master_key = None
