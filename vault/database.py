"""
SQLite Database engine for DevListen in WAL Mode.
Provides read/write concurrency isolation and bi-temporal schema management.
"""
import os
import sqlite3
from typing import Optional

def get_db_path() -> str:
    appdata = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
    vault_dir = os.path.join(appdata, "DevListen")
    os.makedirs(vault_dir, exist_ok=True)
    return os.path.join(vault_dir, "context_vault.db")

class VaultDatabase:
    """
    Manages SQLite connections with WAL mode and robust schema migrations.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
        self._init_database()

    def get_connection(self, read_only: bool = False) -> sqlite3.Connection:
        """
        Returns a configured SQLite connection.
        If read_only is True, opens in URI read-only mode so it NEVER locks writers.
        """
        if read_only:
            uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        else:
            conn = sqlite3.connect(self.db_path, timeout=10.0)

        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """Initializes WAL mode and creates the bi-temporal knowledge graph schema."""
        with sqlite3.connect(self.db_path) as conn:
            # 1. Enable Write-Ahead Logging for high-concurrency
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")

            # 2. Schema definition
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS meetings (
                uuid TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                platform TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                summary_encrypted BLOB
            );

            CREATE TABLE IF NOT EXISTS utterances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_uuid TEXT NOT NULL,
                speaker TEXT NOT NULL, -- 'USER' or 'ATTENDEE'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                text_encrypted BLOB NOT NULL,
                FOREIGN KEY (meeting_uuid) REFERENCES meetings(uuid) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS entities (
                name TEXT PRIMARY KEY,
                category TEXT, -- 'FEATURE', 'PERSON', 'ARCH', 'BUG'
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                meeting_uuid TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                proposed_by TEXT,
                agreed_by TEXT,
                status TEXT CHECK(status IN ('ACTIVE', 'SUPERSEDED', 'REJECTED', 'PROPOSED')),
                effective_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                superseded_at TIMESTAMP,
                superseded_by_id TEXT,
                FOREIGN KEY (meeting_uuid) REFERENCES meetings(uuid),
                FOREIGN KEY (entity_name) REFERENCES entities(name)
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_entity ON decisions(entity_name);
            CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
            CREATE INDEX IF NOT EXISTS idx_utterances_meeting ON utterances(meeting_uuid);
            """)
            conn.commit()
