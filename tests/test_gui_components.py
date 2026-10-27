import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage, Note
from lunariz.gui.theme import format_relative_time, sanitize_snippet


@pytest.fixture
def temp_workspace():
    tmp_dir = Path(tempfile.mkdtemp(prefix="lunar_gui_test_"))
    config = LunarConfig(base_dir=tmp_dir)
    storage = NoteStorage(config)
    yield storage, config
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_format_relative_time():
    now_iso = datetime.now(timezone.utc).isoformat()
    assert format_relative_time(now_iso) == "Just now"

    mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    assert "m ago" in format_relative_time(mins_ago)

    hours_ago = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert "h ago" in format_relative_time(hours_ago)

    days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    assert "d ago" in format_relative_time(days_ago)


def test_sanitize_snippet():
    raw_markdown = """# Heading One
Here is **bold** text and `inline code`.

```python
def foo():
    pass
```

> A calm quote
- [ ] Task item 1
- [x] Task item 2
"""
    clean = sanitize_snippet(raw_markdown)
    assert "#" not in clean
    assert "```" not in clean
    assert "Task item 1" in clean
    assert len(clean) <= 90


def test_duplicate_note(temp_workspace):
    storage, _ = temp_workspace
    original = storage.create_note(
        title="Architecture Blueprint",
        content="# Architecture Blueprint\nDetails of the architecture.",
        tags=["arch", "design"],
    )

    cloned = storage.duplicate_note(original.id)
    assert cloned is not None
    assert cloned.id != original.id
    assert cloned.title == "Architecture Blueprint (Copy)"
    assert cloned.tags == ["arch", "design"]
    assert "Details of the architecture." in cloned.content

    # Check that both files exist on disk
    all_notes = storage.list_notes()
    assert len(all_notes) == 2


def test_export_as_html(temp_workspace):
    storage, config = temp_workspace
    note = storage.create_note(
        title="Meeting Notes",
        content="""# Meeting Notes
- [ ] Item 1
- [x] Item 2

Here is some `code` and **bold** text.
""",
        tags=["meeting"],
    )

    out_file = config.base_dir / "export_test.html"
    result_path = storage.export_as_html(note, out_file)

    assert result_path.exists()
    html_text = result_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "<title>Meeting Notes - Lunariz</title>" in html_text
    assert "<h1>Meeting Notes</h1>" in html_text
    assert "Item 1" in html_text
    assert "Item 2" in html_text
