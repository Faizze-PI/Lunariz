import os
import json
import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from lunariz.core.config import LunarConfig
from lunariz.core.storage import Note, NoteStorage


class NoteHistory:
    def __init__(self, config: Optional[LunarConfig] = None):
        self.config = config or LunarConfig()
        self.config.ensure_directories()

    def _get_history_dir(self, note_id: str) -> Path:
        note_hist = self.config.history_dir / note_id
        note_hist.mkdir(parents=True, exist_ok=True)
        return note_hist

    def record_snapshot(self, note: Note, prev_content: Optional[str] = None) -> None:
        """Save an incremental micro-snapshot if content changed."""
        if prev_content is not None and prev_content.strip() == note.content.strip():
            return  # No content changes

        hist_dir = self._get_history_dir(note.id)
        now_utc = datetime.now(timezone.utc)
        base_ts = now_utc.strftime("%Y%m%d_%H%M%S_%f")
        ts_str = base_ts
        counter = 0
        while (hist_dir / f"{ts_str}.json").exists():
            counter += 1
            ts_str = f"{base_ts}_{counter:04d}"

        diff = []
        if prev_content is not None:
            diff = list(difflib.unified_diff(
                prev_content.splitlines(keepends=True),
                note.content.splitlines(keepends=True),
                fromfile="previous",
                tofile="current",
                n=3,
            ))

        snapshot_data = {
            "id": ts_str,
            "timestamp": now_utc.isoformat(),
            "note_id": note.id,
            "char_count": len(note.content),
            "word_count": len(note.content.split()),
            "content": note.content,
            "has_diff": len(diff) > 0,
            "diff": "".join(diff[:50]),  # Store snippet of diff
        }

        snapshot_file = hist_dir / f"{ts_str}.json"
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)

    def list_snapshots(self, note_id: str) -> List[Dict[str, Any]]:
        """List all saved snapshots for a note, sorted chronologically."""
        hist_dir = self.config.history_dir / note_id
        if not hist_dir.exists():
            return []

        snapshots = []
        for file in sorted(hist_dir.glob("*.json"), reverse=True):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    snapshots.append({
                        "id": data.get("id", file.stem),
                        "timestamp": data.get("timestamp", ""),
                        "char_count": data.get("char_count", 0),
                        "word_count": data.get("word_count", 0),
                        "has_diff": data.get("has_diff", False),
                    })
            except Exception:
                continue
        return snapshots

    def get_snapshot_content(self, note_id: str, snapshot_id: str) -> Optional[str]:
        """Fetch the full content of a specific snapshot."""
        hist_dir = self.config.history_dir / note_id
        snapshot_file = hist_dir / f"{snapshot_id}.json"
        if not snapshot_file.exists():
            return None

        try:
            with open(snapshot_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("content")
        except Exception:
            return None

    def restore_snapshot(self, note: Note, snapshot_id: str, storage: NoteStorage) -> Optional[Note]:
        """Revert note content to a previous snapshot, recording a backup snapshot first."""
        target_content = self.get_snapshot_content(note.id, snapshot_id)
        if target_content is None:
            return None

        # Backup current state first
        self.record_snapshot(note)

        # Apply target content
        note.content = target_content
        return storage.write_note(note)
