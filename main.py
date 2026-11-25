"""
DevListen — Master Edge AI Meeting Copilot Entrypoint.
Orchestrates:
1. Dual-Stream Audio Engine (WASAPI Loopback + User Microphone).
2. Dual-Engine Offline ASR (faster-whisper INT8 + RealtimeSTT Dual-VAD).
3. Local Bi-Temporal Knowledge Graph & 384-d ONNX Vector RAG.
4. Encrypted SQLite WAL Storage (DPAPI + AES-256-GCM).
5. Obsidian Glass Sidecar HUD with OS screen-share exclusion.
"""
import os
import sys
import uuid
import threading
import multiprocessing

multiprocessing.freeze_support()
try:
    import torch.multiprocessing as mp
    mp.freeze_support()
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Slot
from pynput import keyboard

from core.audio_engine import ResilientAudioEngine
from core.hardware_profiler import probe_hardware
from core.local_transcriber import LocalTranscriber
from core.realtimestt_transcriber import AdvancedRealtimeTranscriber
from core.question_detector import QuestionDetector
from core.turn_aggregator import ConversationalTurnAggregator
from vault.crypto import VaultCrypto
from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.decision_extractor import DecisionExtractor
from vault.commitment_extractor import CommitmentExtractor
from vault.semantic_search import SemanticSearchEngine
from ui.executive_sidecar import ExecutiveSidecar
from ui.system_tray import DevListenSystemTray
from export.meeting_exporter import MeetingExporter


class HotkeySignaler(QObject):
    toggle_hud = Signal()
    export_minutes = Signal()
    quit_app = Signal()


class TranscribeSignaler(QObject):
    caption_ready = Signal(str, str, bool)
    nudge_ready = Signal(str, str)
    decision_ready = Signal(dict)
    commitment_ready = Signal(dict)
    audio_levels = Signal(float, float)


def format_context_html(ctx: dict) -> str:
    entity = ctx.get("entity", "Entity")
    curr = ctx.get("current_decision")
    history = ctx.get("history", [])

    if not curr and not history:
        return f"<div style='color: #ECEFF1; font-size: 11px;'>No recorded decisions found for <b>{entity}</b>.</div>"

    html = "<div style='font-family: sans-serif; font-size: 11px;'>"
    html += f"<div style='color: #818CF8; font-weight: bold; font-size: 12px; margin-bottom: 4px;'>{entity}</div>"

    if curr:
        html += f"""
        <div style='color: #10B981; font-weight: bold; margin-bottom: 2px;'>
            • CURRENT TRUTH [{curr['status']}]:
        </div>
        <div style='color: #F1F5F9; margin-left: 8px; margin-bottom: 6px;'>
            {curr['summary']}
        </div>
        """

    if history:
        html += "<div style='color: #94A3B8; font-weight: bold; margin-top: 4px;'>• PRIOR HISTORY:</div>"
        for h in history:
            html += f"""
            <div style='color: #64748B; font-size: 10px; margin-left: 8px;'>
                <s>{h['summary']}</s> <span style='color: #F43F5E;'>[SUPERSEDED]</span>
            </div>
            """

    html += "</div>"
    return html


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. Initialize Local Encrypted Vault & Knowledge Graph
    db = VaultDatabase()
    graph = TemporalDecisionGraph(db)
    extractor = DecisionExtractor(graph)
    commitment_extractor = CommitmentExtractor(db)
    semantic_engine = SemanticSearchEngine(db)

    # 2. Hybrid Semantic + Exact Query Handler
    def query_resolver(query_text: str) -> str:
        matches = semantic_engine.search(query_text, top_k=1, min_similarity=0.48)
        if matches:
            entity_name = matches[0]["entity_name"]
        else:
            with db.get_connection(read_only=True) as conn:
                cursor = conn.execute(
                    "SELECT name FROM entities WHERE name LIKE ? LIMIT 1",
                    (f"%{query_text}%",)
                )
                row = cursor.fetchone()
                entity_name = row["name"] if row else query_text

        ctx = graph.get_entity_context(entity_name)
        return format_context_html(ctx)

    # 3. Launch Executive Copilot Sidecar & System Tray
    copilot = ExecutiveSidecar(on_query_callback=query_resolver)
    copilot.show()
    tray = DevListenSystemTray()

    hw_profile = probe_hardware()
    copilot.set_tier_badge(
        hw_profile.tier_label,
        f"Hardware: {hw_profile.cpu_cores}T CPU, {hw_profile.total_ram_gb}GB RAM\n"
        f"GPU: {hw_profile.gpu_name} ({hw_profile.gpu_vram_gb}GB VRAM)\n"
        f"Engine: {hw_profile.recommended_model}"
    )

    def run_background_indexing():
        try:
            semantic_engine.index_all_pending()
        except Exception as e:
            print(f"[DevListen Indexer Error] {e}")

    threading.Thread(target=run_background_indexing, daemon=True, name="DevListen-Indexer").start()

    # 4. Session & Signal Bridge
    meeting_lock = threading.Lock()
    active_meeting_uuid = str(uuid.uuid4())
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
            (active_meeting_uuid, "Live Edge AI Session", "Local")
        )
        conn.commit()

    transcribe_signaler = TranscribeSignaler()
    transcribe_signaler.caption_ready.connect(copilot.add_or_update_stream_card)
    transcribe_signaler.nudge_ready.connect(copilot.show_ambient_nudge)
    transcribe_signaler.decision_ready.connect(copilot.add_decision_card)
    transcribe_signaler.commitment_ready.connect(copilot.add_commitment_card)
    transcribe_signaler.audio_levels.connect(copilot.update_audio_levels)

    signaler = HotkeySignaler()
    signaler.toggle_hud.connect(lambda: copilot.setVisible(not copilot.isVisible()))

    def handle_export_minutes():
        try:
            out_file = MeetingExporter.export_latest_meeting(db)
            if out_file:
                print(f"[DevListen Export] Meeting minutes saved to: {out_file}")
                tray.show_message("DevListen • Minutes Exported", f"Saved summary to:\n{os.path.basename(out_file)}")
            else:
                tray.show_message("DevListen • Export", "No meeting data found to export.")
        except Exception as e:
            print(f"[DevListen Export Error] {e}")

    signaler.export_minutes.connect(handle_export_minutes)
    copilot.export_requested.connect(handle_export_minutes)
    tray.toggle_hud_requested.connect(lambda: copilot.setVisible(not copilot.isVisible()))
    tray.opacity_changed.connect(copilot.set_opacity)
    tray.export_requested.connect(handle_export_minutes)

    def check_proactive_nudge(text: str):
        if QuestionDetector.is_question(text):
            matches = semantic_engine.search(text, top_k=1, min_similarity=0.68)
            if matches:
                matched_entity = matches[0]["entity_name"]
                ctx = graph.get_entity_context(matched_entity)
                transcribe_signaler.nudge_ready.emit(format_context_html(ctx), text)

    def persist_and_analyze(text: str, speaker: str):
        try:
            encrypted_bytes = VaultCrypto.encrypt_data(text)
            with meeting_lock:
                m_uuid = active_meeting_uuid
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO utterances (meeting_uuid, speaker, text_encrypted) VALUES (?, ?, ?)",
                    (m_uuid, speaker, encrypted_bytes)
                )
                conn.commit()

            dec = extractor.analyze_utterance(text, speaker=speaker, meeting_uuid=m_uuid)
            if dec:
                semantic_engine.index_decision(dec["decision_id"], f"{dec['entity']}: {dec['summary']}")
                transcribe_signaler.decision_ready.emit(dec)

            commit = commitment_extractor.analyze_utterance(text, speaker=speaker, meeting_uuid=m_uuid)
            if commit:
                transcribe_signaler.commitment_ready.emit(commit)

            check_proactive_nudge(text)
        except Exception as db_err:
            print(f"[DevListen Vault Error] {db_err}")

    # 5. Dual-Stream ASR Pipeline
    def on_remote_statement_update(current_text: str, speaker_id: str):
        transcribe_signaler.caption_ready.emit(current_text, speaker_id, False)

    def on_remote_statement_final(full_statement: str, speaker_id: str):
        print(f"\n[DevListen Attendees] [{speaker_id}]: {full_statement}\n")
        transcribe_signaler.caption_ready.emit(full_statement, speaker_id, True)
        persist_and_analyze(full_statement, speaker_id)

    turn_aggregator = ConversationalTurnAggregator(
        silence_timeout=4.5,
        max_paragraph_words=120,
        on_turn_update=on_remote_statement_update,
        on_turn_finalize=on_remote_statement_final
    )

    def on_remote_transcription(text: str, source: str, pcm_data=None):
        turn_aggregator.feed(text, "ATTENDEES")

    remote_transcriber = LocalTranscriber(model_size="base", on_transcript_callback=on_remote_transcription)
    remote_transcriber.start()

    def on_user_interim(text: str, source: str):
        if len(text.split()) >= 2:
            turn_aggregator.flush()
        transcribe_signaler.caption_ready.emit(text, "YOU", False)

    def on_user_final(text: str, source: str):
        print(f"\n[DevListen Mic] [YOU]: {text}\n")
        transcribe_signaler.caption_ready.emit(text, "YOU", True)
        persist_and_analyze(text, "YOU")

    user_transcriber = AdvancedRealtimeTranscriber(
        model="base",
        realtime_model="tiny",
        on_interim_callback=on_user_interim,
        on_final_callback=on_user_final
    )
    user_transcriber.start()

    # 6. Shutdown & Global Hotkeys
    def shutdown():
        for fn in (
            turn_aggregator.flush,
            user_transcriber.stop,
            remote_transcriber.stop,
            audio_engine.stop,
            copilot.close,
        ):
            try:
                fn()
            except Exception:
                pass
        app.quit()
        os._exit(0)

    signaler.quit_app.connect(shutdown)
    copilot.quit_requested.connect(shutdown)
    tray.quit_requested.connect(shutdown)

    hotkeys = keyboard.GlobalHotKeys({
        '<alt>+<shift>+l': lambda: signaler.toggle_hud.emit(),
        '<alt>+<shift>+<space>': lambda: signaler.toggle_hud.emit(),
        '<alt>+<shift>+e': lambda: signaler.export_minutes.emit(),
        '<alt>+<shift>+q': lambda: signaler.quit_app.emit()
    })
    threading.Thread(target=hotkeys.run, daemon=True).start()

    # 7. Audio Capture Engine
    def on_speech_chunk(pcm_chunk, source):
        if source == "REMOTE":
            remote_transcriber.feed_chunk(pcm_chunk, source)

    audio_engine = ResilientAudioEngine(
        on_speech_chunk=on_speech_chunk,
        on_levels_chunk=lambda mic, call: transcribe_signaler.audio_levels.emit(mic, call)
    )
    audio_engine.start()

    print("DevListen Edge Copilot running (100% Offline).")
    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
