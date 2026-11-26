"""
DevListen — Voice-Synchronized 1-Click Video Recording & Demo Runner.
Simulates a live multi-speaker engineering sync with realistic neural AI voices:
1. Synthesizes distinct neural voices for [ATTENDEES] (en-US-AndrewNeural) & [YOU] (en-US-BrianNeural) via edge-tts.
2. Plays audio natively on Windows (winmm MCI) in sync with live streaming word captions & waveform energy.
3. Triggers Zero-Click Proactive RAG Nudge + Natural Suggested Response when a question is asked.
4. Auto-extracts an architectural decision & action item into the Bi-Temporal Graph & Inspector.
"""
import os
import sys
import uuid
import time
import ctypes
import asyncio
import threading
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.semantic_search import SemanticSearchEngine
from vault.context_formatter import format_context_html
from ui.desktop_studio import DevListenStudio


class DemoSignaler(QObject):
    stream_card = Signal(str, str, bool)
    audio_levels = Signal(float, float)
    nudge = Signal(str, str)
    decision = Signal(dict)
    commitment = Signal(dict)


def get_mp3_duration_sec(mp3_path: str) -> float:
    """Queries exact MP3 duration in seconds via Windows winmm MCI."""
    try:
        winmm = ctypes.windll.winmm
        alias = f"len_{int(time.time() * 1000)}"
        buf = ctypes.create_unicode_buffer(64)
        winmm.mciSendStringW(f'open "{mp3_path}" type mpegvideo alias {alias}', None, 0, None)
        winmm.mciSendStringW(f'set {alias} time format milliseconds', None, 0, None)
        winmm.mciSendStringW(f'status {alias} length', buf, 64, None)
        winmm.mciSendStringW(f'close {alias}', None, 0, None)
        ms = int(buf.value)
        return max(1.0, ms / 1000.0)
    except Exception:
        return 4.5


def play_mp3_blocking(mp3_path: str):
    """Plays an MP3 file cleanly using Windows winmm MCI without extra dependencies."""
    winmm = ctypes.windll.winmm
    alias = f"devlisten_demo_{int(time.time() * 1000)}"
    winmm.mciSendStringW(f'open "{mp3_path}" type mpegvideo alias {alias}', None, 0, None)
    winmm.mciSendStringW(f'play {alias} wait', None, 0, None)
    winmm.mciSendStringW(f'close {alias}', None, 0, None)


def speak_fallback_sapi(text: str):
    """Offline fallback using built-in Windows System.Speech if edge-tts is unavailable."""
    safe = text.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{safe}')"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prepare_demo_audio(script: list, cache_dir: str) -> list:
    """Pre-generates and caches neural AI voice MP3 clips via edge-tts."""
    os.makedirs(cache_dir, exist_ok=True)
    paths = []
    try:
        import edge_tts

        async def _synth_all():
            for idx, item in enumerate(script):
                fname = item.get("cache_name", f"turn_{idx}.mp3")
                out_file = os.path.join(cache_dir, fname)
                if not os.path.exists(out_file) or os.path.getsize(out_file) < 512:
                    voice = "en-US-BrianNeural" if item["speaker"] == "YOU" else "en-US-AndrewNeural"
                    comm = edge_tts.Communicate(item["text"], voice)
                    await comm.save(out_file)
                paths.append(out_file)

        asyncio.run(_synth_all())
    except Exception as e:
        print(f"[DevListen Demo] Neural TTS unavailable ({e}), using offline Windows Speech fallback.")
        paths = [None] * len(script)
    return paths


def run_demo():
    app = QApplication(sys.argv)

    # 1. Initialize Vault & Pre-seed Bi-Temporal Knowledge Graph
    db = VaultDatabase()
    graph = TemporalDecisionGraph(db)
    semantic_engine = SemanticSearchEngine(db)

    m_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
            (m_uuid, "Product & Architecture Review", "Teams")
        )
        conn.commit()

    dec1 = graph.record_decision(
        entity_name="GraphQL Caching",
        summary="Use Redis for response caching across all endpoints.",
        status="SUPERSEDED",
        proposed_by="Alex",
        agreed_by="Team",
        meeting_uuid=m_uuid
    )
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

    sig = DemoSignaler()
    sig.stream_card.connect(sidecar.add_or_update_stream_card)
    sig.audio_levels.connect(sidecar.update_audio_levels)
    sig.nudge.connect(sidecar.show_ambient_nudge)
    sig.decision.connect(sidecar.add_decision_card)
    sig.commitment.connect(sidecar.add_commitment_card)

    script = [
        {
            "speaker": "ATTENDEES",
            "text": "All right team, we need to finalize our database and caching tier before the v2 release. Are we sticking with Redis?",
            "event": "rag_redis",
        },
        {
            "speaker": "YOU",
            "text": "I thought we agreed to hold off on Redis until Schema v2 lands to avoid unnecessary memory overhead.",
            "event": None,
        },
        {
            "speaker": "ATTENDEES",
            "text": "Wait, what did we decide about the GraphQL caching strategy last month?",
            "event": "rag_nudge",
            "cache_name": "turn_2.mp3",
        },
        {
            "speaker": "YOU",
            "text": "For GraphQL Caching, we decided to hold off on Redis until Schema v2 lands to avoid memory overhead.",
            "event": None,
            "cache_name": "reply_graphql.mp3",
        },
        {
            "speaker": "ATTENDEES",
            "text": "Got it, makes total sense. Let's deploy the Kubernetes cluster with an NGINX ingress controller hooked up to PostgreSQL.",
            "event": "decision",
            "cache_name": "turn_3.mp3",
        },
        {
            "speaker": "ATTENDEES",
            "text": "Devanshu, can you update the ADR documentation and sync with the DevOps team by tomorrow morning?",
            "event": "commitment",
            "cache_name": "turn_4.mp3",
        },
        {
            "speaker": "YOU",
            "text": "On it. I'll export the meeting minutes and share the updated ADR with the infra squad.",
            "event": None,
            "cache_name": "turn_5.mp3",
        },
    ]

    cache_dir = os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "DevListen", "demo_voices")

    def orchestrate():
        print("[DevListen Demo] Preparing neural AI voices...")
        audio_paths = prepare_demo_audio(script, cache_dir)
        time.sleep(1.0)

        for item, mp3 in zip(script, audio_paths):
            spk = item["speaker"]
            full_text = item["text"]
            words = full_text.split()

            # Measure exact audio duration so captions appear RIGHT AFTER each word is spoken (realistic ASR lag)
            duration_sec = get_mp3_duration_sec(mp3) if (mp3 and os.path.exists(mp3)) else max(2.0, len(words) * 0.36)

            # Start audio playback on a worker thread
            if mp3 and os.path.exists(mp3):
                play_t = threading.Thread(target=play_mp3_blocking, args=(mp3,), daemon=True)
            else:
                play_t = threading.Thread(target=speak_fallback_sapi, args=(full_text,), daemon=True)
            play_t.start()

            # Initial ~220ms ASR recognition lag + waveform warm-up before first words appear
            if spk == "YOU":
                sig.audio_levels.emit(0.75, 0.0)
            else:
                sig.audio_levels.emit(0.0, 0.72)
            time.sleep(0.24)

            # Pace streaming word chunks proportionally across remaining audio duration
            remaining = max(0.5, duration_sec - 0.30)
            chunk_size = 2
            chunks = [words[:i] for i in range(chunk_size, len(words), chunk_size)]
            per_step = remaining / max(1, len(chunks) + 1)

            for partial in chunks:
                if not play_t.is_alive():
                    break
                if spk == "YOU":
                    sig.audio_levels.emit(0.75, 0.0)
                else:
                    sig.audio_levels.emit(0.0, 0.72)
                sig.stream_card.emit(" ".join(partial) + "...", spk, False)
                time.sleep(per_step)

            play_t.join()
            sig.stream_card.emit(full_text, spk, True)
            sig.audio_levels.emit(0.0, 0.0)

            # Fire synchronized AI events
            if item["event"] == "rag_redis":
                ctx = graph.get_entity_context("GraphQL Caching")
                sig.nudge.emit(format_context_html(ctx), full_text)
                time.sleep(0.9)
            elif item["event"] == "rag_nudge":
                ctx = graph.get_entity_context("GraphQL Caching")
                sig.nudge.emit(format_context_html(ctx), full_text)
                time.sleep(1.1)
            elif item["event"] == "decision":
                sig.decision.emit({
                    "entity": "Kubernetes Ingress",
                    "status": "ACTIVE",
                    "summary": "Deployed Kubernetes cluster with NGINX ingress controller hooked up to PostgreSQL.",
                    "proposed_by": "Architecture Lead",
                    "agreed_by": "Team",
                })
                sig.nudge.emit(
                    "<div style='color:#818CF8;font-weight:bold;'>Kubernetes Ingress</div>"
                    "<div style='color:#10B981;font-weight:bold;'>• CURRENT TRUTH [ACTIVE]:</div>"
                    "<div style='color:#ECEFF1;'>Deploy Kubernetes cluster with NGINX ingress controller hooked up to PostgreSQL.</div>",
                    "Decision Logged: Kubernetes Ingress"
                )
            elif item["event"] == "commitment":
                sig.commitment.emit({
                    "assignee": "Devanshu",
                    "task": "Update the ADR documentation and sync with the DevOps team by tomorrow morning.",
                })
                sig.nudge.emit(
                    "<div style='color:#818CF8;font-weight:bold;'>Action Item • @Devanshu</div>"
                    "<div style='color:#10B981;font-weight:bold;'>• CURRENT TRUTH [ACTIVE]:</div>"
                    "<div style='color:#ECEFF1;'>Export the meeting minutes and share the updated ADR with the infra squad.</div>",
                    full_text
                )
                time.sleep(0.8)

            time.sleep(0.75)

        print("[DevListen Demo] Simulation complete!")

    threading.Thread(target=orchestrate, daemon=True, name="DevListen-DemoVoice").start()

    print("==================================================")
    print("DevListen Voice-Synchronized Demo Active")
    print("• Neural AI Voices: ATTENDEES + YOU")
    print("• Live Waveform, Streaming Captions & RAG Nudge")
    print("==================================================")

    sys.exit(app.exec())


if __name__ == "__main__":
    run_demo()
