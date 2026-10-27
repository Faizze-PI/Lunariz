import pytest
import tempfile
from pathlib import Path
from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage, Note
from lunariz.core.indexer import NoteIndexer
from lunariz.core.tasks import TaskEngine
from lunariz.core.history import NoteHistory
from lunariz.core.search import MultiTokenSearch


@pytest.fixture
def temp_config(tmp_path):
    config = LunarConfig(base_dir=tmp_path)
    config.ensure_directories()
    return config


def test_note_creation_and_atomic_write(temp_config):
    storage = NoteStorage(temp_config)
    note = storage.create_note(
        title="Sprint Planning",
        content="# Sprint Planning\n\nDiscussing v1 release #dev #launch.\n- [ ] Deploy container",
        tags=["sprint"],
        is_pinned=True,
    )

    assert note.id is not None
    assert note.title == "Sprint Planning"
    assert "dev" in note.tags
    assert "launch" in note.tags
    assert "sprint" in note.tags
    assert note.is_pinned is True
    assert note.path.exists()

    # Read back from disk
    read_note = storage.read_note_from_path(note.path)
    assert read_note is not None
    assert read_note.title == "Sprint Planning"
    assert read_note.is_pinned is True
    assert "Discussing v1 release" in read_note.content


def test_note_soft_delete(temp_config):
    storage = NoteStorage(temp_config)
    note = storage.create_note("Temporary Note", "Some content to delete")
    assert note.path.exists()

    deleted = storage.delete_note(note.id)
    assert deleted is True
    assert not note.path.exists()
    assert len(list(temp_config.trash_dir.glob("*.md"))) == 1


def test_sqlite_indexer_and_fts(temp_config):
    storage = NoteStorage(temp_config)
    indexer = NoteIndexer(temp_config)

    n1 = storage.create_note("Docker Tutorial", "How to run alpine container #devops #docker")
    n2 = storage.create_note("Recipe for Pasta", "Cook pasta in boiling salted water #cooking")

    updated = indexer.sync_from_storage(storage)
    assert updated == 2

    # FTS query for "docker"
    results = indexer.search("docker")
    assert len(results) == 1
    assert results[0]["title"] == "Docker Tutorial"

    # Search with tag filter
    results_tag = indexer.search("", tag="cooking")
    assert len(results_tag) == 1
    assert results_tag[0]["title"] == "Recipe for Pasta"

    # All tags check
    tags = indexer.get_all_tags()
    tag_names = [t["tag"] for t in tags]
    assert "devops" in tag_names
    assert "cooking" in tag_names


def test_task_extraction_and_toggle(temp_config):
    storage = NoteStorage(temp_config)
    content = """# Team Roadmap
- [ ] Setup CI/CD pipeline
- [x] Configure SQLite WAL mode
- [ ] Write integration tests
"""
    note = storage.create_note("Roadmap", content)
    tasks = TaskEngine.extract_tasks_from_note(note)
    assert len(tasks) == 3
    assert tasks[0].is_done is False
    assert tasks[1].is_done is True

    # Toggle task
    toggled, updated_note = TaskEngine.toggle_task(note, "Setup CI/CD", storage=storage)
    assert toggled is True
    assert "- [x] Setup CI/CD pipeline" in updated_note.content

    # Check Kanban projection
    kanban = TaskEngine.project_kanban(updated_note)
    assert "Pending" in kanban
    assert "Completed" in kanban
    assert len(kanban["Completed"]) == 2


def test_time_machine_history(temp_config):
    storage = NoteStorage(temp_config)
    history = NoteHistory(temp_config)

    note = storage.create_note("Draft Article", "Initial draft paragraph.")
    history.record_snapshot(note)

    # Edit note
    note.content = "Second revised paragraph with major updates."
    history.record_snapshot(note, prev_content="Initial draft paragraph.")
    storage.write_note(note)

    snapshots = history.list_snapshots(note.id)
    assert len(snapshots) == 2

    # Restore snapshot 1
    oldest_snap_id = snapshots[-1]["id"]
    restored = history.restore_snapshot(note, oldest_snap_id, storage)
    assert restored is not None
    assert restored.content == "Initial draft paragraph."


def test_multi_token_search(temp_config):
    storage = NoteStorage(temp_config)
    n1 = storage.create_note("Quarterly Financial Review", "Discussing revenue and client retention #finance")
    n2 = storage.create_note("DevOps Retrospective", "Docker performance and server costs #devops")

    all_notes = [n1, n2]
    # Query "revenue finance" should match n1 with high score
    ranked = MultiTokenSearch.rank_notes(all_notes, "revenue finance")
    assert len(ranked) >= 1
    assert ranked[0].title == "Quarterly Financial Review"
