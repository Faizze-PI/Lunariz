import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from lunariz.core.config import LunarConfig
from lunariz.core.storage import Note, NoteStorage


class NoteIndexer:
    def __init__(self, config: Optional[LunarConfig] = None):
        self.config = config or LunarConfig()
        self.config.ensure_directories()
        self.db_path = self.config.db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Open a SQLite connection with WAL mode enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Create tables and FTS5 virtual table if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS notes_meta (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                slug TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_pinned INTEGER DEFAULT 0,
                is_archived INTEGER DEFAULT 0,
                content_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS note_tags (
                note_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (note_id, tag),
                FOREIGN KEY (note_id) REFERENCES notes_meta(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes_meta(is_pinned, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON note_tags(tag);

            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                id UNINDEXED,
                title,
                content,
                tags,
                tokenize='unicode61 remove_diacritics 2'
            );
            """)

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def index_note(self, note: Note) -> None:
        """Insert or update a single note in the index."""
        content_hash = self._compute_hash(note.content)
        tags_str = " ".join(note.tags)

        with self._get_connection() as conn:
            # Upsert into notes_meta
            conn.execute("""
                INSERT INTO notes_meta (id, title, slug, path, created_at, updated_at, is_pinned, is_archived, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    slug=excluded.slug,
                    path=excluded.path,
                    updated_at=excluded.updated_at,
                    is_pinned=excluded.is_pinned,
                    is_archived=excluded.is_archived,
                    content_hash=excluded.content_hash;
            """, (
                note.id,
                note.title,
                note.path.stem,
                str(note.path),
                note.created_at,
                note.updated_at,
                1 if note.is_pinned else 0,
                1 if note.is_archived else 0,
                content_hash,
            ))

            # Update tags
            conn.execute("DELETE FROM note_tags WHERE note_id = ?;", (note.id,))
            for tag in note.tags:
                conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?);", (note.id, tag))

            # Update FTS5
            conn.execute("DELETE FROM notes_fts WHERE id = ?;", (note.id,))
            conn.execute("""
                INSERT INTO notes_fts (id, title, content, tags)
                VALUES (?, ?, ?, ?);
            """, (note.id, note.title, note.content, tags_str))

    def remove_note(self, note_id: str) -> None:
        """Remove note from all index tables."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM notes_meta WHERE id = ?;", (note_id,))
            conn.execute("DELETE FROM note_tags WHERE note_id = ?;", (note_id,))
            conn.execute("DELETE FROM notes_fts WHERE id = ?;", (note_id,))

    def sync_from_storage(self, storage: NoteStorage) -> int:
        """Synchronize SQLite cache with disk files in a single fast transaction."""
        disk_notes = storage.list_notes()
        disk_ids = {n.id: n for n in disk_notes}
        updated_count = 0

        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                cached_rows = conn.execute("SELECT id, content_hash FROM notes_meta;").fetchall()
                cached_map = {row["id"]: row["content_hash"] for row in cached_rows}

                # Delete notes no longer on disk
                for cached_id in cached_map:
                    if cached_id not in disk_ids:
                        conn.execute("DELETE FROM notes_meta WHERE id = ?;", (cached_id,))
                        conn.execute("DELETE FROM note_tags WHERE note_id = ?;", (cached_id,))
                        conn.execute("DELETE FROM notes_fts WHERE id = ?;", (cached_id,))

                # Batch insert/update new or changed notes
                for note in disk_notes:
                    curr_hash = self._compute_hash(note.content)
                    if note.id not in cached_map or cached_map[note.id] != curr_hash:
                        tags_str = " ".join(note.tags)
                        conn.execute("""
                            INSERT INTO notes_meta (id, title, slug, path, created_at, updated_at, is_pinned, is_archived, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                title=excluded.title,
                                slug=excluded.slug,
                                path=excluded.path,
                                updated_at=excluded.updated_at,
                                is_pinned=excluded.is_pinned,
                                is_archived=excluded.is_archived,
                                content_hash=excluded.content_hash;
                        """, (
                            note.id,
                            note.title,
                            note.path.stem,
                            str(note.path),
                            note.created_at,
                            note.updated_at,
                            1 if note.is_pinned else 0,
                            1 if note.is_archived else 0,
                            curr_hash,
                        ))

                        conn.execute("DELETE FROM note_tags WHERE note_id = ?;", (note.id,))
                        for tag in note.tags:
                            conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?);", (note.id, tag))

                        conn.execute("DELETE FROM notes_fts WHERE id = ?;", (note.id,))
                        conn.execute("""
                            INSERT INTO notes_fts (id, title, content, tags)
                            VALUES (?, ?, ?, ?);
                        """, (note.id, note.title, note.content, tags_str))
                        updated_count += 1

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return updated_count

    def search(self, query: str, tag: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Run full-text search with BM25 ranking and optional tag filtering."""
        with self._get_connection() as conn:
            clean_q = query.strip()
            if not clean_q:
                # Return recent notes if query is empty
                if tag:
                    sql = """
                        SELECT m.* FROM notes_meta m
                        JOIN note_tags t ON m.id = t.note_id
                        WHERE t.tag = ?
                        ORDER BY m.is_pinned DESC, m.updated_at DESC
                        LIMIT ?;
                    """
                    rows = conn.execute(sql, (tag.lower(), limit)).fetchall()
                else:
                    sql = """
                        SELECT * FROM notes_meta
                        ORDER BY is_pinned DESC, updated_at DESC
                        LIMIT ?;
                    """
                    rows = conn.execute(sql, (limit,)).fetchall()
            else:
                # Clean query for FTS5 (escape quotes and format tokens)
                fts_query = " ".join([f'"{tok}"*' for tok in clean_q.split() if tok.isalnum() or "-" in tok])
                if not fts_query:
                    fts_query = f'"{clean_q}"'

                if tag:
                    sql = """
                        SELECT m.*, bm25(notes_fts) as rank
                        FROM notes_fts f
                        JOIN notes_meta m ON f.id = m.id
                        JOIN note_tags t ON m.id = t.note_id
                        WHERE notes_fts MATCH ? AND t.tag = ?
                        ORDER BY m.is_pinned DESC, rank ASC
                        LIMIT ?;
                    """
                    rows = conn.execute(sql, (fts_query, tag.lower(), limit)).fetchall()
                else:
                    sql = """
                        SELECT m.*, bm25(notes_fts) as rank
                        FROM notes_fts f
                        JOIN notes_meta m ON f.id = m.id
                        WHERE notes_fts MATCH ?
                        ORDER BY m.is_pinned DESC, rank ASC
                        LIMIT ?;
                    """
                    rows = conn.execute(sql, (fts_query, limit)).fetchall()

            results = []
            for r in rows:
                tags_rows = conn.execute("SELECT tag FROM note_tags WHERE note_id = ?;", (r["id"],)).fetchall()
                note_tags = [tr["tag"] for tr in tags_rows]
                results.append({
                    "id": r["id"],
                    "title": r["title"],
                    "path": r["path"],
                    "tags": note_tags,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "is_pinned": bool(r["is_pinned"]),
                })
            return results

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Return all unique tags with usage counts."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT tag, COUNT(note_id) as count
                FROM note_tags
                GROUP BY tag
                ORDER BY count DESC, tag ASC;
            """).fetchall()
            return [{"tag": r["tag"], "count": r["count"]} for r in rows]
