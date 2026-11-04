"""Local SQLite persistence for conversations and messages.

All access goes through :class:`ChatDatabase`. The connection is created with
``check_same_thread=False`` and guarded by a lock, so worker threads may write
generation results safely.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    model_id    TEXT NOT NULL DEFAULT '',
    model_mode  TEXT NOT NULL DEFAULT 'auto' CHECK (model_mode IN ('auto', 'manual')),
    title_is_auto INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    model_id        TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
"""


@dataclass
class Conversation:
    id: str
    title: str
    created_at: float
    updated_at: float
    model_id: str = ""
    model_mode: str = "auto"
    title_is_auto: bool = True


@dataclass
class Message:
    id: int
    conversation_id: str
    role: str
    content: str
    created_at: float
    model_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ChatDatabase:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        with self._conn:
            self._conn.executescript(SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- conversations -----------------------------------------------------

    def create_conversation(
        self, title: str = "New chat", model_id: str = "", model_mode: str = "auto"
    ) -> Conversation:
        now = time.time()
        conv = Conversation(uuid.uuid4().hex, title, now, now, model_id, model_mode, True)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, model_id, model_mode,"
                " title_is_auto) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (conv.id, conv.title, conv.created_at, conv.updated_at, model_id, model_mode),
            )
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return self._conversation(row) if row else None

    def list_conversations(self, query: str = "") -> list[Conversation]:
        """Most recently updated first. ``query`` matches titles and message text."""
        with self._lock:
            if query.strip():
                like = f"%{_escape_like(query.strip())}%"
                rows = self._conn.execute(
                    "SELECT * FROM conversations c WHERE c.title LIKE ? ESCAPE '\\' OR EXISTS ("
                    " SELECT 1 FROM messages m WHERE m.conversation_id = c.id"
                    " AND m.content LIKE ? ESCAPE '\\') ORDER BY c.updated_at DESC",
                    (like, like),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC"
                ).fetchall()
        return [self._conversation(r) for r in rows]

    def rename_conversation(self, conversation_id: str, title: str, auto: bool = False) -> None:
        title = " ".join(title.split())[:120] or "Untitled chat"
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET title = ?, title_is_auto = ? WHERE id = ?",
                (title, int(auto), conversation_id),
            )

    def set_conversation_model(self, conversation_id: str, model_id: str, mode: str) -> None:
        if mode not in ("auto", "manual"):
            raise ValueError(f"invalid model mode: {mode}")
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET model_id = ?, model_mode = ? WHERE id = ?",
                (model_id, mode, conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def touch(self, conversation_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), conversation_id)
            )

    # -- messages ------------------------------------------------------------

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        now = time.time()
        meta = metadata or {}
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at, model_id, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, role, content, now, model_id, json.dumps(meta)),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        return Message(cur.lastrowid, conversation_id, role, content, now, model_id, meta)

    def update_message(
        self,
        message_id: int,
        content: str,
        model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        sets, args = ["content = ?"], [content]
        if model_id is not None:
            sets.append("model_id = ?")
            args.append(model_id)
        if metadata is not None:
            sets.append("metadata = ?")
            args.append(json.dumps(metadata))
        args.append(message_id)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", args)

    def delete_message(self, message_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def messages(self, conversation_id: str) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
            ).fetchall()
        return [
            Message(
                r["id"],
                r["conversation_id"],
                r["role"],
                r["content"],
                r["created_at"],
                r["model_id"],
                json.loads(r["metadata"] or "{}"),
            )
            for r in rows
        ]

    def count_messages(self, conversation_id: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()[0]

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(
            row["id"],
            row["title"],
            row["created_at"],
            row["updated_at"],
            row["model_id"],
            row["model_mode"],
            bool(row["title_is_auto"]),
        )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def suggest_title(first_message: str, limit: int = 48) -> str:
    """Derive a short conversation title from the user's first message.

    Small models are unreliable at summarising into titles, so smolchat uses a
    deterministic heuristic: first sentence/line, trimmed on a word boundary.
    """
    text = " ".join(first_message.strip().split())
    if not text:
        return "New chat"
    for sep in ("\n", ". ", "? ", "! "):
        idx = text.find(sep)
        if 0 < idx < limit:
            text = text[: idx + (1 if sep.strip() in "?!" else 0)]
            break
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text[0].upper() + text[1:]
