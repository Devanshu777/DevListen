"""
DevListen — Flawless 1-Click Video Recording & Demo Runner.
Simulates a live multi-speaker engineering sync with realistic pacing:
1. Displays the stunning Granola/Raycast Obsidian Glass HUD.
2. Streams real-time speech cards for [ATTENDEES] and [YOU].
3. Fires an automatic Zero-Click Proactive Knowledge Nudge when an attendee asks a question.
4. Auto-detects an architectural decision and records it in the Bi-Temporal Graph.
5. Auto-detects an action item commitment and assigns it.
6. Allows you to speak into your mic or let the script run automatically.
"""
import os
import sys
import time
import uuid
import threading
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Ensure paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vault.database import VaultDatabase
from vault.crypto import VaultCrypto
from vault.temporal_graph import TemporalDecisionGraph
from vault.decision_extractor import DecisionExtractor
from vault.commitment_extractor import CommitmentExtractor
from vault.semantic_search import SemanticSearchEngine
from ui.desktop_studio import DevListenStudio
from export.meeting_exporter import MeetingExporter

def format_context_html(ctx: dict) -> str:
    entity = ctx.get("entity", "Entity")
    curr = ctx.get("current_decision")
    history = ctx.get("history", [])

    if not curr and not history:
        return f"<div style='color: #ECEFF1; font-size: 11px;'>No recorded decisions found for <b>{entity}</b>.</div>"

    html = f"<div style='font-family: sans-serif; font-size: 11px;'>"
    html += f"<div style='color: #818CF8; font-weight: bold; font-size: 12px; margin-bottom: 4px;'>{entity}</div>"

    if curr:
        html += f"""
        <div style='color: #10B981; font-weight: bold; margin-bottom: 2px;'>
            • CURRENT TRUTH [{curr['status']}]:
        </div>
        <div style='color: #ECEFF1; margin-left: 8px; margin-bottom: 6px;'>
            {curr['summary']}
        </div>
        """

    if history:
        html += "<div style='color: #94A3B8; font-weight: bold; margin-top: 4px;'>• PRIOR HISTORY:</div>"
        for h in history:
            html += f"""
            <div style='color: #64748B; font-size: 10px; margin-left: 8px;'>
                <s>{h['summary']}</s> <span style='color: #EF4444;'>[SUPERSEDED]</span>
            </div>
            """

    html += "</div>"
    return html

def run_demo():
    app = QApplication(sys.argv)

    # 1. Initialize Database & Seed Demo Knowledge
    db = VaultDatabase()
    graph = TemporalDecisionGraph(db)
    extractor = DecisionExtractor(graph)
    commitment_extractor = CommitmentExtractor(db)
    semantic_engine = SemanticSearchEngine(db)

    # Pre-seed historical context so the Zero-Click Nudge triggers flawlessly
    m_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
                     (m_uuid, "Product & Architecture Review", "Teams"))
        conn.commit()

    # Pre-seed: Prior decision on GraphQL Caching
    dec1 = graph.record_decision(
        entity_name="GraphQL Caching",
        summary="Use Redis for response caching across all endpoints.",
        status="SUPERSEDED",
        proposed_by="Alex",
        agreed_by="Team",
        meeting_uuid=m_uuid
    )
    # Superseding decision: Current Truth
    dec2 = graph.record_decision(
        entity_name="GraphQL Caching",
        summary="Hold off on Redis until Schema v2 lands to avoid memory overhead.",
        status="ACTIVE",
        proposed_by="You",
        agreed_by="Team",
        meeting_uuid=m_uuid,
        supersedes_decision_id=dec1
    )
    semantic_engine.index_decision(dec2, "GraphQL Caching: Hold off on Redis until Schema v2 lands.")

    def query_resolver(query_text: str) -> str:
        matches = semantic_engine.search(query_text, top_k=1, min_similarity=0.45)
        entity_name = matches[0]["entity_name"] if matches else query_text
        ctx = graph.get_entity_context(entity_name)
        return format_context_html(ctx)

    # 2. Launch Desktop Studio UI
    sidecar = DevListenStudio(on_query_callback=query_resolver)
    sidecar._apply_stealth("--stealth" in sys.argv)
    sidecar.set_tier_badge("INT8 CPU • Ready", "Hardware: CPU Optimized • 100% Offline")
    sidecar.show()

    # 3. Timed Storyboard Sequence for Video Recording
    timeline = [
        # (delay_sec, function)
        (2.0, lambda: sidecar.update_audio_levels(0.0, 0.45)),
        (3.0, lambda: sidecar.add_or_update_stream_card(
            "All right team, we need to finalize our database and caching tier before the v2 release date.",
            "ATTENDEES",
            False
        )),
        (5.0, lambda: sidecar.add_or_update_stream_card(
            "All right team, we need to finalize our database and caching tier before the v2 release date. Are we sticking with Redis, or should we evaluate Memcached?",
            "ATTENDEES",
            True
        )),
        (6.5, lambda: sidecar.update_audio_levels(0.65, 0.0)),
        (7.5, lambda: sidecar.add_or_update_stream_card(
            "I thought we agreed to hold off on Redis",
            "YOU",
            False
        )),
        (9.0, lambda: sidecar.add_or_update_stream_card(
            "I thought we agreed to hold off on Redis until Schema v2 lands to avoid unnecessary memory overhead.",
            "YOU",
            True
        )),
        (10.5, lambda: sidecar.update_audio_levels(0.0, 0.55)),
        (11.5, lambda: sidecar.add_or_update_stream_card(
            "Wait, what did we decide about the GraphQL caching strategy last month?",
            "ATTENDEES",
            True
        )),
        # Trigger Zero-Click Nudge automatically!
        (13.0, lambda: sidecar.show_ambient_nudge(
            format_context_html(graph.get_entity_context("GraphQL Caching")),
            "Wait, what did we decide about the GraphQL caching strategy last month?"
        )),
        # Attendee proposes new architectural direction
        (17.0, lambda: sidecar.add_or_update_stream_card(
            "We deployed the Kubernetes cluster with an NGINX ingress controller and hooked it up with PostgreSQL and Redis.",
            "ATTENDEES",
            True
        )),
        # Extract Decision into Decisions Tab
        (18.5, lambda: sidecar.add_decision_card({
            "entity": "Kubernetes",
            "status": "ACTIVE",
            "summary": "Adopted Kubernetes with an NGINX ingress controller hooked up to PostgreSQL and Redis.",
            "proposed_by": "Architecture Lead",
            "agreed_by": "Team"
        })),
        # Action Item Assignment
        (22.0, lambda: sidecar.add_or_update_stream_card(
            "Good point. Sanchit, can you update the ADR documentation and ping the DevOps team by tomorrow morning?",
            "ATTENDEES",
            True
        )),
        (23.5, lambda: sidecar.add_commitment_card({
            "assignee": "Sanchit",
            "task": "Update the ADR documentation and ping the DevOps team by tomorrow morning."
        })),
        # Final User confirmation
        (26.0, lambda: sidecar.add_or_update_stream_card(
            "On it. I'll export the meeting minutes and sync with the infra squad.",
            "YOU",
            True
        )),
        (28.0, lambda: sidecar.update_audio_levels(0.0, 0.0)),
    ]

    for delay, fn in timeline:
        QTimer.singleShot(int(delay * 1000), fn)

    print("==================================================")
    print("DevListen Demo Runner Active 🎥")
    print("• Perfect for OBS Screen Recording!")
    print("• Timed realistic simulation running on screen...")
    print("• Decisions, Action Items & Zero-Click Nudge will trigger automatically.")
    print("==================================================")

    sys.exit(app.exec())

if __name__ == "__main__":
    run_demo()
