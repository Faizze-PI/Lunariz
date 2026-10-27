import os
import re
import shutil
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Union
from lunariz.core.config import LunarConfig


@dataclass
class Note:
    id: str
    title: str
    content: str
    path: Path
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    is_pinned: bool = False
    is_archived: bool = False

    @property
    def snippet(self) -> str:
        """Return a 2-line clean preview snippet."""
        lines = [line.strip() for line in self.content.splitlines() if line.strip()]
        # Skip the first line if it represents the title
        if lines and (lines[0].lstrip("#").strip() == self.title or lines[0] == self.title):
            lines = lines[1:]
        return " ".join(lines[:2])[:120] if lines else ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON responses and SQLite caching."""
        return {
            "id": self.id,
            "title": self.title,
            "path": str(self.path),
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_pinned": self.is_pinned,
            "is_archived": self.is_archived,
            "snippet": self.snippet,
            "content": self.content,
        }


class NoteStorage:
    def __init__(self, config: Optional[LunarConfig] = None):
        self.config = config or LunarConfig()
        self.config.ensure_directories()

    @staticmethod
    def extract_title(content: str, fallback: str = "Untitled Note") -> str:
        """Infer note title from the first non-empty line."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                clean = re.sub(r"^#+\s*", "", stripped).strip()
                if clean:
                    return clean
        return fallback

    @staticmethod
    def extract_tags(content: str) -> List[str]:
        """Extract inline #hashtags while ignoring markdown headers (# Header)."""
        tags = set()
        # Match words starting with # not preceded by non-whitespace (ignore ## headers)
        matches = re.findall(r"(?:^|\s)#([a-zA-Z0-9_\-\/]+)", content)
        for tag in matches:
            t = tag.strip().lower()
            if t and not t.isdigit():
                tags.add(t)
        return sorted(list(tags))

    @staticmethod
    def slugify(title: str) -> str:
        """Produce a safe filesystem filename."""
        slug = re.sub(r"[^\w\-_]", "-", title.strip().lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug or "untitled"

    def _generate_unique_path(self, title: str, note_id: Optional[str] = None) -> Path:
        """Generate a collision-free path inside the notes directory."""
        slug = self.slugify(title)
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base_name = f"{date_prefix}-{slug}"
        candidate = self.config.notes_dir / f"{base_name}.md"

        counter = 1
        while candidate.exists():
            # If the candidate file has the same note_id inside, we reuse it
            if note_id and candidate.name.startswith(f"{note_id}-"):
                break
            candidate = self.config.notes_dir / f"{base_name}-{counter}.md"
            counter += 1

        return candidate

    def parse_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        """Extract YAML frontmatter if present, returning metadata and body."""
        meta = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                front = parts[1]
                body = parts[2].lstrip("\r\n")
                for line in front.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == "tags":
                            meta["tags"] = [t.strip().lstrip("#").lower() for t in v.strip("[]").split(",") if t.strip()]
                        elif k in ("pinned", "is_pinned"):
                            meta["is_pinned"] = v.lower() in ("true", "1", "yes")
                        elif k in ("archived", "is_archived"):
                            meta["is_archived"] = v.lower() in ("true", "1", "yes")
                        elif k == "id":
                            meta["id"] = v
                        elif k in ("created_at", "updated_at"):
                            meta[k] = v
                        elif k == "title":
                            meta["title"] = v
        return meta, body

    def serialize_note(self, note: Note) -> str:
        """Serialize note with minimalist metadata header if pinned/tagged."""
        front = []
        if note.is_pinned:
            front.append("pinned: true")
        if note.is_archived:
            front.append("archived: true")
        if note.id:
            front.append(f"id: {note.id}")
        if note.title:
            front.append(f"title: {note.title}")
        if note.tags:
            front.append(f"tags: [{', '.join(note.tags)}]")

        if front:
            return f"---\n{chr(10).join(front)}\n---\n\n{note.content}"
        return note.content

    def read_note_from_path(self, path: Path) -> Optional[Note]:
        """Read a .md file from disk and parse into a Note object."""
        if not path.exists() or not path.is_file():
            return None

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception:
            return None

        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        ctime = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()

        meta, body = self.parse_frontmatter(raw_text)
        title = meta.get("title") or self.extract_title(body, fallback=path.stem)
        tags = set(self.extract_tags(body))
        if "tags" in meta:
            tags.update(meta["tags"])

        note_id = meta.get("id", path.stem)
        created_at = meta.get("created_at", ctime)
        updated_at = meta.get("updated_at", mtime)
        is_pinned = meta.get("is_pinned", False)
        is_archived = meta.get("is_archived", False)

        return Note(
            id=note_id,
            title=title,
            content=body,
            path=path,
            tags=sorted(list(tags)),
            created_at=created_at,
            updated_at=updated_at,
            is_pinned=is_pinned,
            is_archived=is_archived,
        )

    def write_note(self, note: Note) -> Note:
        """Atomically write note to disk using temp file + os.replace."""
        now_iso = datetime.now(timezone.utc).isoformat()
        note.updated_at = now_iso
        if not note.created_at:
            note.created_at = now_iso

        if not note.path or not note.path.parent.exists():
            note.path = self._generate_unique_path(note.title, note.id)

        serialized = self.serialize_note(note)

        # Write to a unique temporary file in the same directory for atomic replace
        unique_token = hashlib.md5(f"{datetime.now(timezone.utc).isoformat()}_{os.getpid()}_{id(note)}".encode()).hexdigest()[:8]
        temp_file = note.path.parent / f".{note.path.stem}_{unique_token}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()

        # Atomic rename with defensive retry backoff for Windows NTFS file locks
        max_retries = 10
        for attempt in range(max_retries):
            try:
                os.replace(temp_file, note.path)
                break
            except (PermissionError, OSError):
                if attempt == max_retries - 1:
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except Exception:
                            pass
                    raise
                import time
                time.sleep(0.015 * (attempt + 1))

        return note

    def create_note(
        self,
        title: str,
        content: str = "",
        tags: Optional[List[str]] = None,
        is_pinned: bool = False,
    ) -> Note:
        """Create and write a new note file."""
        now_iso = datetime.now(timezone.utc).isoformat()
        # If title is in content or empty, derive properly
        if not content and title:
            content = f"# {title}\n\n"
        elif not title and content:
            title = self.extract_title(content)

        slug = self.slugify(title)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        note_id = f"{slug}-{date_str[-6:]}"

        path = self._generate_unique_path(title, note_id)

        all_tags = set(tags or [])
        all_tags.update(self.extract_tags(content))

        note = Note(
            id=note_id,
            title=title,
            content=content,
            path=path,
            tags=sorted(list(all_tags)),
            created_at=now_iso,
            updated_at=now_iso,
            is_pinned=is_pinned,
        )
        return self.write_note(note)

    def delete_note(self, note_id_or_title: str) -> bool:
        """Soft-delete note by moving to ~/.lunar/.trash/."""
        note = self.get_note(note_id_or_title)
        if not note or not note.path.exists():
            return False

        trash_path = self.config.trash_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{note.path.name}"
        shutil.move(str(note.path), str(trash_path))
        return True

    def duplicate_note(self, note_or_id: Union[Note, str]) -> Optional[Note]:
        """Create a duplicate copy of a note."""
        note = note_or_id if isinstance(note_or_id, Note) else self.get_note(note_or_id)
        if not note:
            return None
        dup_title = f"{note.title} (Copy)"
        return self.create_note(title=dup_title, content=note.content, tags=list(note.tags), is_pinned=False)

    @staticmethod
    def export_as_html(note: Note, output_path: Optional[Path] = None, is_dark: bool = True) -> Path:
        """Export note to standalone, beautifully styled HTML."""
        import html
        bg = "#161614" if is_dark else "#FBF9F5"
        card = "#1E1E1B" if is_dark else "#FFFFFF"
        text = "#E6E4DE" if is_dark else "#282725"
        accent = "#818CF8" if is_dark else "#D97706"
        muted = "#8A8780" if is_dark else "#7D7A75"

        body_html = html.escape(note.content).replace("\n", "<br>")
        tags_pills = "".join([f"<span class='tag'>#{html.escape(t)}</span>" for t in note.tags])

        rendered = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(note.title)} - Lunariz</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: {bg}; color: {text}; display: flex; justify-content: center; padding: 40px 20px; }}
  .container {{ background: {card}; max-width: 720px; width: 100%; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }}
  h1 {{ color: {accent}; margin-top: 0; }}
  .meta {{ color: {muted}; font-size: 13px; margin-bottom: 24px; }}
  .tag {{ background: rgba(129, 140, 248, 0.15); color: {accent}; padding: 3px 8px; border-radius: 4px; font-weight: bold; margin-right: 6px; }}
  .content {{ line-height: 1.6; font-size: 15px; }}
</style>
</head>
<body>
<div class="container">
  <h1>{html.escape(note.title)}</h1>
  <div class="meta">Updated: {note.updated_at[:16].replace('T', ' ')} &nbsp; {tags_pills}</div>
  <div class="content">{body_html}</div>
</div>
</body>
</html>"""
        target = output_path or (note.path.parent / f"{note.slug}.html")
        Path(target).write_text(rendered, encoding="utf-8")
        return Path(target)

    def list_notes(self) -> List[Note]:
        """List all valid Markdown notes on disk."""
        notes = []
        if not self.config.notes_dir.exists():
            return notes

        for file_path in sorted(self.config.notes_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            if file_path.name.startswith("."):
                continue
            note = self.read_note_from_path(file_path)
            if note:
                notes.append(note)
        return notes

    def get_note(self, id_or_query: str) -> Optional[Note]:
        """Find a note by ID, filename stem, or title match."""
        q = id_or_query.strip().lower()

        # Direct file check
        direct_path = self.config.notes_dir / f"{id_or_query}.md"
        if direct_path.exists():
            return self.read_note_from_path(direct_path)

        for note in self.list_notes():
            if note.id.lower() == q or note.path.stem.lower() == q or note.title.lower() == q:
                return note

        # Fallback to substring matching
        for note in self.list_notes():
            if q in note.title.lower() or q in note.id.lower():
                return note

        return None
