"""
DevListen Meeting Minutes & Action Item Exporter.
Exports structured meeting summaries with:
- Identified Attendees
- Active & Superseded Architectural Decisions
- Extracted Action Items
- Full Decrypted Transcript with Timestamps
"""
import os
import datetime
from vault.database import VaultDatabase
from vault.crypto import VaultCrypto

class MeetingExporter:
    @staticmethod
    def export_latest_meeting(db: VaultDatabase) -> str:
        """Exports the latest meeting session to Markdown and returns the file path."""
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents", "DevListen_Exports")
        os.makedirs(docs_dir, exist_ok=True)

        with db.get_connection(read_only=True) as conn:
            # 1. Fetch latest meeting
            m_row = conn.execute("SELECT uuid, title, platform, start_time FROM meetings ORDER BY start_time DESC LIMIT 1").fetchone()
            if not m_row:
                return ""

            m_uuid = m_row["uuid"]
            m_title = m_row["title"]
            m_platform = m_row["platform"] or "Local"
            m_start = m_row["start_time"]

            # 2. Fetch utterances
            u_rows = conn.execute(
                "SELECT speaker, timestamp, text_encrypted FROM utterances WHERE meeting_uuid = ? ORDER BY id ASC",
                (m_uuid,)
            ).fetchall()

            # 3. Fetch decisions
            d_rows = conn.execute(
                "SELECT entity_name, summary, proposed_by, agreed_by, status, effective_from FROM decisions WHERE meeting_uuid = ? ORDER BY rowid ASC",
                (m_uuid,)
            ).fetchall()

            # 4. Fetch action items & commitments
            try:
                act_rows = conn.execute(
                    "SELECT assignee, task_description, completed FROM action_items WHERE meeting_uuid = ? ORDER BY rowid ASC",
                    (m_uuid,)
                ).fetchall()
            except Exception:
                act_rows = []

        # Decrypt utterances & collect attendees
        transcript_entries = []
        attendees = set()
        for ur in u_rows:
            try:
                dec_text = VaultCrypto.decrypt_data(ur["text_encrypted"])
                spk = ur["speaker"]
                attendees.add(spk)
                transcript_entries.append((spk, ur["timestamp"], dec_text))
            except Exception:
                pass

        # Build markdown document
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in m_title if c.isalnum() or c in (' ', '_', '-')).strip()
        filename = f"Meeting_{safe_title}_{now_str}.md"
        out_path = os.path.join(docs_dir, filename)

        md = []
        md.append(f"# 📋 Meeting Summary: {m_title}")
        md.append(f"**Platform:** {m_platform}  ")
        md.append(f"**Date:** {m_start}  ")
        md.append(f"**Exported:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        md.append(f"**Attendees:** {', '.join(sorted(attendees)) if attendees else 'Attendees Recorded'}\n")
        md.append("---\n")

        # Decisions Section
        md.append("## 🎯 Architectural Decisions & Outcomes\n")
        if d_rows:
            for d in d_rows:
                status_icon = "🟢 [ACTIVE]" if d["status"] == "ACTIVE" else "🔴 [SUPERSEDED]" if d["status"] == "SUPERSEDED" else "⚪ [REJECTED]"
                md.append(f"### {status_icon} **{d['entity_name']}**")
                md.append(f"- **Summary:** {d['summary']}")
                md.append(f"- **Proposed By:** {d.get('proposed_by', 'Team')} • **Status:** {d['status']}\n")
        else:
            md.append("*No formal decisions were recorded in this session.*\n")

        md.append("---\n")

        # Action Items Section
        md.append("## ⚡ Action Items & Commitments\n")
        if act_rows:
            for a in act_rows:
                check = "[x]" if a["completed"] else "[ ]"
                md.append(f"- {check} **{a['assignee']}**: {a['task_description']}")
            md.append("\n")
        else:
            md.append("*No verbal action items or commitments were detected in this session.*\n")

        md.append("---\n")

        # Full Transcript Section
        md.append("## 💬 Complete Meeting Transcript\n")
        if transcript_entries:
            for spk, ts, txt in transcript_entries:
                time_part = str(ts)[11:19] if len(str(ts)) >= 19 else str(ts)
                md.append(f"**[{time_part}] {spk}:** {txt}\n")
        else:
            md.append("*No speech transcript recorded for this session.*\n")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        return out_path
