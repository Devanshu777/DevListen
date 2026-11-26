"""
Isolated unit tests for DecisionExtractor, CommitmentExtractor, and QuestionDetector.
"""
import uuid
from pathlib import Path

from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.decision_extractor import DecisionExtractor
from vault.commitment_extractor import CommitmentExtractor
from core.question_detector import QuestionDetector


def _setup(tmp_path: Path):
    db = VaultDatabase(db_path=str(tmp_path / "extractors.db"))
    m_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
            (m_uuid, "Test Sync", "Local"),
        )
        conn.commit()
    return db, TemporalDecisionGraph(db), m_uuid


def test_decision_extractor_patterns(tmp_path: Path):
    _, graph, m_uuid = _setup(tmp_path)
    extractor = DecisionExtractor(graph)

    rej = extractor.analyze_utterance(
        "Alex proposed using MongoDB, but the architect rejected because we need ACID transactions.",
        speaker="USER",
        meeting_uuid=m_uuid,
    )
    assert rej is not None
    assert rej["entity"] == "Mongodb"
    assert rej["status"] == "REJECTED"

    adopt = extractor.analyze_utterance(
        "We deployed the Kubernetes cluster with an NGINX ingress controller.",
        speaker="ATTENDEES",
        meeting_uuid=m_uuid,
    )
    assert adopt is not None
    assert adopt["entity"] == "Kubernetes"
    assert adopt["status"] == "ACTIVE"

    upgrade = extractor.analyze_utterance(
        "We need to upgrade the dependency of Guava from 4.1 to 4.37",
        speaker="USER",
        meeting_uuid=m_uuid,
    )
    assert upgrade is not None
    assert "4.1 to 4.37" in upgrade["summary"]


def test_decision_extractor_ignores_invalid_and_casual_inputs(tmp_path: Path):
    _, graph, m_uuid = _setup(tmp_path)
    extractor = DecisionExtractor(graph)

    for text in ["", "   ", "ok", "I think that will cost us $10 or something."]:
        assert extractor.analyze_utterance(text, speaker="USER", meeting_uuid=m_uuid) is None


def test_commitment_extractor_patterns_and_edge_cases(tmp_path: Path):
    db, _, m_uuid = _setup(tmp_path)
    ce = CommitmentExtractor(db)

    c1 = ce.analyze_utterance("I will update the ADR documentation before the release.", "USER", m_uuid)
    assert c1 is not None
    assert c1["assignee"] == "USER"

    c2 = ce.analyze_utterance("Alex will verify the staging deployment logs.", "USER", m_uuid)
    assert c2 is not None
    assert c2["assignee"] == "Alex"

    c3 = ce.analyze_utterance("We need to test the failover script tomorrow.", "ATTENDEES", m_uuid)
    assert c3 is not None
    assert c3["assignee"] == "Team"

    # Short / incomplete sentences should be ignored
    assert ce.analyze_utterance("I'll fix it.", "USER", m_uuid) is None
    assert ce.analyze_utterance("", "USER", m_uuid) is None

    actions = ce.get_actions_for_meeting(m_uuid)
    assert len(actions) == 3


def test_question_detector():
    assert QuestionDetector.is_question("What did we decide about Redis caching?") is True
    assert QuestionDetector.is_question("Why did the architect reject MongoDB") is True
    assert QuestionDetector.is_question("Status on the Kubernetes migration") is True
    assert QuestionDetector.is_question("Let's deploy the service.") is False
    assert QuestionDetector.is_question("ok?") is False
    assert QuestionDetector.is_question("") is False
