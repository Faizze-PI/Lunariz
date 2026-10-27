import sys
import os
import io
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Callable

# Ensure Windows terminal uses UTF-8 encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage, Note
from lunariz.core.indexer import NoteIndexer
from lunariz.core.tasks import TaskEngine
from lunariz.core.history import NoteHistory
from lunariz.core.search import MultiTokenSearch

console = Console()
err_console = Console(stderr=True)


def output_json(success: bool, data: any = None, error: Optional[str] = None) -> None:
    """Print pure, deterministic JSON envelope to stdout."""
    payload = {
        "success": success,
        "data": data,
        "error": error,
    }
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _resolve_add_input(args) -> tuple[str, str]:
    """Helper to resolve note title and content from args or stdin."""
    title = args.title or ""
    content = args.content or ""

    if args.stdin or (not sys.stdin.isatty() and not content):
        piped_input = sys.stdin.read()
        if piped_input.strip():
            content = piped_input
    return title, content


def cmd_add(args, storage: NoteStorage, indexer: NoteIndexer, **kwargs) -> int:
    title, content = _resolve_add_input(args)

    if not title and not content:
        msg = "Must provide title or content (or piped stdin)."
        if args.json:
            output_json(False, error=msg)
        else:
            err_console.print(f"[red]Error: {msg}[/red]")
        return 1

    tags = [t.strip().lstrip("#").lower() for t in args.tags.split(",") if t.strip()] if args.tags else []
    note = storage.create_note(title=title, content=content, tags=tags, is_pinned=args.pinned)
    indexer.index_note(note)

    if args.json:
        output_json(True, data=note.to_dict())
    else:
        console.print(f"[green]✔ Note created:[/green] [bold]{note.title}[/bold] [dim]({note.id})[/dim]")
        if note.tags:
            tag_badges = " ".join([f"[blue]#{t}[/blue]" for t in note.tags])
            console.print(f"  Tags: {tag_badges}")
    return 0


def cmd_list(args, storage: NoteStorage, indexer: NoteIndexer, **kwargs) -> int:
    indexer.sync_from_storage(storage)
    results = indexer.search(query="", tag=args.tag, limit=args.limit)

    if args.pinned:
        results = [r for r in results if r.get("is_pinned")]

    if args.json:
        output_json(True, data=results)
        return 0

    if not results:
        console.print("[dim]No notes found.[/dim]")
        return 0

    table = Table(title="Lunariz Notes", show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Pin", justify="center", width=4)
    table.add_column("Title", style="bold", ratio=3)
    table.add_column("Tags", style="cyan", ratio=2)
    table.add_column("Updated", style="dim", ratio=2)
    table.add_column("ID", style="dim", ratio=2)

    for r in results:
        pin = "📌" if r.get("is_pinned") else ""
        tags_str = " ".join([f"#{t}" for t in r.get("tags", [])])
        updated = r.get("updated_at", "")[:16].replace("T", " ")
        table.add_row(pin, r["title"], tags_str, updated, r["id"])

    console.print(table)
    return 0


def cmd_get(args, storage: NoteStorage, **kwargs) -> int:
    note = storage.get_note(args.id_or_title)
    if not note:
        if args.json:
            output_json(False, error=f"Note not found: {args.id_or_title}")
        else:
            err_console.print(f"[red]Error: Note '{args.id_or_title}' not found.[/red]")
        return 1

    if args.json:
        output_json(True, data=note.to_dict())
        return 0

    if args.raw:
        sys.stdout.write(note.content + "\n")
        sys.stdout.flush()
        return 0

    pin_str = " 📌" if note.is_pinned else ""
    tags_str = " ".join([f"[cyan]#{t}[/cyan]" for t in note.tags])
    panel_title = f"{note.title}{pin_str}"

    console.print(Panel(
        Markdown(note.content),
        title=panel_title,
        subtitle=f"ID: {note.id} | {tags_str} | Updated: {note.updated_at[:16].replace('T', ' ')}",
        border_style="magenta",
        padding=(1, 2),
    ))
    return 0


def cmd_search(args, storage: NoteStorage, indexer: NoteIndexer, **kwargs) -> int:
    indexer.sync_from_storage(storage)
    results = indexer.search(query=args.query, tag=args.tag, limit=args.limit)

    if args.json:
        output_json(True, data=results)
        return 0

    if not results:
        console.print(f"[dim]No matching notes for '{args.query}'.[/dim]")
        return 0

    console.print(f"[bold green]Found {len(results)} note(s) matching '{args.query}':[/bold green]\n")
    for r in results:
        pin = "📌 " if r.get("is_pinned") else ""
        tags_str = " ".join([f"[cyan]#{t}[/cyan]" for t in r.get("tags", [])])
        console.print(f"• {pin}[bold]{r['title']}[/bold] [dim]({r['id']})[/dim] {tags_str}")
    return 0


def cmd_edit(args, storage: NoteStorage, indexer: NoteIndexer, history: NoteHistory, **kwargs) -> int:
    note = storage.get_note(args.id_or_title)
    if not note:
        if args.json:
            output_json(False, error=f"Note '{args.id_or_title}' not found.")
        else:
            err_console.print(f"[red]Error: Note '{args.id_or_title}' not found.[/red]")
        return 1

    history.record_snapshot(note)

    if args.append:
        note.content = f"{note.content.rstrip()}\n\n{args.append}\n"
    elif args.content is not None:
        note.content = args.content

    if args.tags is not None:
        new_tags = [t.strip().lstrip("#").lower() for t in args.tags.split(",") if t.strip()]
        note.tags = sorted(list(set(note.tags + new_tags)))

    if args.pinned is not None:
        note.is_pinned = args.pinned

    storage.write_note(note)
    indexer.index_note(note)

    if args.json:
        output_json(True, data=note.to_dict())
    else:
        console.print(f"[green]✔ Note updated:[/green] [bold]{note.title}[/bold]")
    return 0


def cmd_delete(args, storage: NoteStorage, indexer: NoteIndexer, **kwargs) -> int:
    note = storage.get_note(args.id_or_title)
    if not note:
        if args.json:
            output_json(False, error=f"Note '{args.id_or_title}' not found.")
        else:
            err_console.print(f"[red]Error: Note '{args.id_or_title}' not found.[/red]")
        return 1

    note_id = note.id
    success = storage.delete_note(note_id)
    if success:
        indexer.remove_note(note_id)
        if args.json:
            output_json(True, data={"id": note_id, "deleted": True})
        else:
            console.print(f"[green]✔ Note '{note.title}' moved to trash.[/green]")
        return 0
    return 1


def cmd_scratch(args, storage: NoteStorage, indexer: NoteIndexer, **kwargs) -> int:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scratch_title = f"{today_str} Scratchpad"
    scratch_note = storage.get_note(scratch_title)

    if not args.thought:
        if scratch_note:
            if args.json:
                output_json(True, data=scratch_note.to_dict())
            else:
                console.print(Panel(Markdown(scratch_note.content), title=f"📝 {scratch_title}", border_style="yellow"))
        else:
            if args.json:
                output_json(True, data=None)
            else:
                console.print(f"[dim]No scratchpad entries for today ({today_str}). Add one: lunar scratch 'Your thought'[/dim]")
        return 0

    now_time = datetime.now().strftime("%I:%M %p")
    new_entry = f"### {now_time}\n{args.thought}\n"

    if scratch_note:
        scratch_note.content = f"{scratch_note.content.rstrip()}\n\n{new_entry}"
        storage.write_note(scratch_note)
    else:
        scratch_note = storage.create_note(
            title=scratch_title,
            content=f"# {scratch_title}\n\n{new_entry}",
            tags=["scratchpad", "daily"],
            is_pinned=True,
        )

    indexer.index_note(scratch_note)

    if args.json:
        output_json(True, data=scratch_note.to_dict())
    else:
        console.print(f"[green]✔ Logged to {scratch_title} at {now_time}:[/green] {args.thought}")
    return 0


def _toggle_task_across_notes(target: str, all_notes: List[Note], storage: NoteStorage) -> tuple[bool, Optional[Note]]:
    """Helper to search and toggle task across notes."""
    for note in all_notes:
        toggled, _ = TaskEngine.toggle_task(note, target, storage=storage)
        if toggled:
            return True, note
    return False, None


def cmd_tasks(args, storage: NoteStorage, **kwargs) -> int:
    all_notes = storage.list_notes()

    # Handle toggle command branch
    if args.toggle:
        target = args.toggle.strip().lower()
        toggled, note = _toggle_task_across_notes(target, all_notes, storage)
        if toggled and note:
            if args.json:
                output_json(True, data={"toggled": True, "query": args.toggle, "note_title": note.title})
            else:
                console.print(f"[green]✔ Toggled task matching '{args.toggle}' in '{note.title}'[/green]")
            return 0

        if args.json:
            output_json(False, error=f"No matching task for: {args.toggle}")
        else:
            err_console.print(f"[red]Error: No matching task found for '{args.toggle}'[/red]")
        return 1

    all_tasks = []
    for note in all_notes:
        all_tasks.extend(TaskEngine.extract_tasks_from_note(note))

    if args.pending:
        all_tasks = [t for t in all_tasks if not t.is_done]
    elif args.done:
        all_tasks = [t for t in all_tasks if t.is_done]

    if args.json:
        output_json(True, data=[t.to_dict() for t in all_tasks])
        return 0

    if not all_tasks:
        console.print("[dim]No tasks found.[/dim]")
        return 0

    table = Table(title="Lunariz Tasks", show_header=True, header_style="bold green")
    table.add_column("Status", justify="center", width=6)
    table.add_column("Task", ratio=3)
    table.add_column("Note Source", style="dim", ratio=2)

    for t in all_tasks:
        status_icon = "[green]✔ Done[/green]" if t.is_done else "[yellow]○ Pending[/yellow]"
        table.add_row(status_icon, t.text, t.note_title)

    console.print(table)
    return 0


def cmd_kanban(args, storage: NoteStorage, **kwargs) -> int:
    note = storage.get_note(args.id_or_title)
    if not note:
        if args.json:
            output_json(False, error=f"Note '{args.id_or_title}' not found.")
        else:
            err_console.print(f"[red]Error: Note '{args.id_or_title}' not found.[/red]")
        return 1

    board = TaskEngine.project_kanban(note)
    if args.json:
        output_data = {col: [t.to_dict() for t in tasks] for col, tasks in board.items()}
        output_json(True, data=output_data)
        return 0

    console.print(f"[bold cyan]Kanban: {note.title}[/bold cyan]\n")
    for col_name, tasks in board.items():
        console.print(f"[bold underline]{col_name}[/bold underline] ({len(tasks)})")
        if not tasks:
            console.print("  [dim](No items)[/dim]")
        for t in tasks:
            check = "✔" if t.is_done else "○"
            console.print(f"  {check} {t.text}")
        console.print()
    return 0


def cmd_history(args, storage: NoteStorage, history: NoteHistory, **kwargs) -> int:
    note = storage.get_note(args.id_or_title)
    if not note:
        if args.json:
            output_json(False, error=f"Note '{args.id_or_title}' not found.")
        else:
            err_console.print(f"[red]Error: Note '{args.id_or_title}' not found.[/red]")
        return 1

    if args.revert:
        restored = history.restore_snapshot(note, args.revert, storage)
        if restored:
            if args.json:
                output_json(True, data=restored.to_dict())
            else:
                console.print(f"[green]✔ Reverted '{note.title}' to snapshot {args.revert}[/green]")
            return 0
        else:
            if args.json:
                output_json(False, error=f"Snapshot '{args.revert}' not found.")
            else:
                err_console.print(f"[red]Error: Snapshot '{args.revert}' not found.[/red]")
            return 1

    snapshots = history.list_snapshots(note.id)
    if args.json:
        output_json(True, data=snapshots)
        return 0

    if not snapshots:
        console.print(f"[dim]No revision history yet for '{note.title}'.[/dim]")
        return 0

    console.print(f"[bold magenta]Revision History: {note.title}[/bold magenta]")
    for snap in snapshots:
        diff_badge = "[cyan]diff[/cyan]" if snap["has_diff"] else ""
        console.print(f"• Snapshot: [bold]{snap['id']}[/bold] | {snap['timestamp'][:19].replace('T', ' ')} | {snap['word_count']} words {diff_badge}")
    return 0


def cmd_mcp(args, **kwargs) -> int:
    from lunariz.agent.mcp_server import run_mcp_server
    return run_mcp_server()


def cmd_app(args, **kwargs) -> int:
    from lunariz.gui.app import run_gui
    return run_gui()


# Command Dispatch Map
COMMAND_HANDLERS: Dict[str, Callable] = {
    "add": cmd_add,
    "list": cmd_list,
    "get": cmd_get,
    "search": cmd_search,
    "edit": cmd_edit,
    "delete": cmd_delete,
    "scratch": cmd_scratch,
    "tasks": cmd_tasks,
    "kanban": cmd_kanban,
    "history": cmd_history,
    "mcp": cmd_mcp,
    "app": cmd_app,
}


def _register_subparsers(subparsers):
    """Modular registration of CLI subparsers."""
    # app
    subparsers.add_parser("app", help="Launch the native Windows Desktop GUI Application")

    # add
    p_add = subparsers.add_parser("add", help="Create a new note")
    p_add.add_argument("title", nargs="?", default="", help="Note title")
    p_add.add_argument("--content", "-c", help="Note body text")
    p_add.add_argument("--tags", "-t", help="Comma-separated tags (e.g. 'work,dev')")
    p_add.add_argument("--pinned", "-p", action="store_true", help="Pin note to top")
    p_add.add_argument("--stdin", action="store_true", help="Read note content from stdin")
    p_add.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # list
    p_list = subparsers.add_parser("list", help="List notes")
    p_list.add_argument("--tag", "-t", help="Filter by tag")
    p_list.add_argument("--pinned", "-p", action="store_true", help="Show only pinned notes")
    p_list.add_argument("--limit", "-n", type=int, default=50, help="Maximum notes to list")
    p_list.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # get
    p_get = subparsers.add_parser("get", help="Read note content")
    p_get.add_argument("id_or_title", help="Note ID, slug, or title")
    p_get.add_argument("--raw", "-r", action="store_true", help="Print raw Markdown content without headers")
    p_get.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # search
    p_search = subparsers.add_parser("search", help="Instant multi-token search")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--tag", "-t", help="Filter results by tag")
    p_search.add_argument("--limit", "-n", type=int, default=20, help="Max results")
    p_search.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # edit
    p_edit = subparsers.add_parser("edit", help="Edit or append to a note")
    p_edit.add_argument("id_or_title", help="Note ID or title")
    p_edit.add_argument("--content", "-c", help="New body content (replaces existing)")
    p_edit.add_argument("--append", "-a", help="Append text to end of note")
    p_edit.add_argument("--tags", "-t", help="Add tags")
    p_edit.add_argument("--pinned", action="store_true", default=None, help="Update pinned status")
    p_edit.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # delete
    p_delete = subparsers.add_parser("delete", help="Soft-delete a note to .trash/")
    p_delete.add_argument("id_or_title", help="Note ID or title")
    p_delete.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # scratch
    p_scratch = subparsers.add_parser("scratch", help="Quick thought scratchpad")
    p_scratch.add_argument("thought", nargs="?", default="", help="Thought to log")
    p_scratch.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # tasks
    p_tasks = subparsers.add_parser("tasks", help="Task and checklist manager")
    p_tasks.add_argument("--pending", action="store_true", help="Show pending tasks only")
    p_tasks.add_argument("--done", action="store_true", help="Show completed tasks only")
    p_tasks.add_argument("--toggle", help="Toggle completion state of a task")
    p_tasks.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # kanban
    p_kanban = subparsers.add_parser("kanban", help="Project note into a Kanban board")
    p_kanban.add_argument("id_or_title", help="Note ID or title")
    p_kanban.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # history
    p_history = subparsers.add_parser("history", help="Local time-machine revision history")
    p_history.add_argument("id_or_title", help="Note ID or title")
    p_history.add_argument("--revert", help="Revert to snapshot ID")
    p_history.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # mcp
    subparsers.add_parser("mcp", help="Run Model Context Protocol (MCP) server for AI agents")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lunar",
        description="Lunariz: Ultra-lightweight, calm desktop and CLI note-taking engine for humans and AI agents.",
    )
    parser.add_argument("--version", action="version", version="Lunariz 1.0.0")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    _register_subparsers(subparsers)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Launch GUI if no command or command is 'app'
    if not args.command or args.command == "app":
        from lunariz.gui.app import run_gui
        return run_gui()

    handler = COMMAND_HANDLERS.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    # Initialize core services
    config = LunarConfig().load_from_file()
    storage = NoteStorage(config)
    indexer = NoteIndexer(config)
    history = NoteHistory(config)

    return handler(
        args=args,
        storage=storage,
        indexer=indexer,
        history=history,
    )


if __name__ == "__main__":
    sys.exit(main())
