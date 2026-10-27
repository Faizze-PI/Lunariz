import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from tkinter import filedialog, messagebox

import customtkinter as ctk

from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage, Note
from lunariz.core.indexer import NoteIndexer
from lunariz.core.tasks import TaskEngine
from lunariz.core.history import NoteHistory
from lunariz.core.search import MultiTokenSearch
from lunariz.gui.theme import THEMES, FONTS, format_relative_time, sanitize_snippet
from lunariz.gui.cards import NoteCard
from lunariz.gui.markdown_view import MarkdownPreviewPane
from lunariz.gui.kanban_view import KanbanBoardView
from lunariz.gui.command_palette import CommandPaletteModal


class LunarDesktopApp(ctk.CTk):
    """
    Industrial-Grade, Ultra-Lightweight Calm Desktop Note-Taking Window.
    Features:
    - Microsecond instant responsiveness.
    - Multi-view canvas: Live Edit, Rich Markdown Typography Preview, and Embedded Kanban.
    - Floating Spotlight Command Palette (Ctrl+K).
    - Note Cards with relative time, active accent indicators, and right-click context menus.
    - Zero vendor lock-in with transparent local Markdown files.
    """

    def __init__(self, config: Optional[LunarConfig] = None):
        super().__init__()

        self.config = config or LunarConfig().load_from_file()
        self.storage = NoteStorage(self.config)
        self.indexer = NoteIndexer(self.config)
        self.history = NoteHistory(self.config)

        self.current_theme_name = self.config.theme
        self.theme = THEMES[self.current_theme_name]
        ctk.set_appearance_mode(self.theme["appearance_mode"])

        # Window settings
        self.title("Lunariz - Calm Desktop Notes")
        self.geometry("1120x720")
        self.minsize(880, 580)

        # State
        self.active_note: Optional[Note] = None
        self.notes: List[Note] = []
        self.selected_tag: Optional[str] = None
        self.search_query: str = ""
        self.auto_save_job: Optional[str] = None
        self.last_sync_mtime: float = 0.0
        self.current_view_mode: str = "✍️ Edit"

        # Build UI layout
        self._build_layout()
        self._setup_global_shortcuts()
        self.refresh_notes_list()

        # Select first note if available
        if self.notes:
            self.select_note(self.notes[0])
        else:
            self.create_new_note()

        # Start periodic background disk check
        self.after(2000, self._poll_disk_changes)

    def _setup_global_shortcuts(self):
        """Register global application accelerators."""
        self.bind("<Control-n>", lambda e: self.create_new_note())
        self.bind("<Control-f>", lambda e: self._focus_search())
        self.bind("<Control-k>", lambda e: self.open_command_palette())
        self.bind("<Control-p>", lambda e: self.open_command_palette())
        self.bind("<Control-s>", lambda e: self._save_active_note_now())
        self.bind("<Control-e>", lambda e: self._set_view_mode("✍️ Edit"))
        self.bind("<Control-Shift-P>", lambda e: self._set_view_mode("👁️ Preview"))
        self.bind("<Control-Shift-K>", lambda e: self._set_view_mode("▦ Kanban"))

    def _focus_search(self):
        self.search_entry.focus()
        self.search_entry.select_range(0, "end")

    def _build_layout(self):
        # Configure grid: Column 0 is sidebar (fixed), Column 1 is editor (expanding)
        self.grid_columnconfigure(0, weight=0, minsize=300)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # -------------------------------------------------------------
        # 1. Left Sidebar
        # -------------------------------------------------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=self.theme["bg_sidebar"])
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar_frame.grid_rowconfigure(3, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # Header: Logo & New Note Button
        self.top_header_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.top_header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        self.top_header_frame.grid_columnconfigure(0, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.top_header_frame,
            text="🌙 Lunariz",
            font=FONTS["title"],
            text_color=self.theme["text_primary"],
        )
        self.logo_label.grid(row=0, column=0, sticky="w")

        self.palette_btn = ctk.CTkButton(
            self.top_header_frame,
            text="⌘K",
            font=("Segoe UI", 11, "bold"),
            width=36,
            height=26,
            fg_color=self.theme["bg_card"],
            hover_color=self.theme["bg_card_hover"],
            text_color=self.theme["text_muted"],
            corner_radius=6,
            command=self.open_command_palette,
        )
        self.palette_btn.grid(row=0, column=1, sticky="e")

        self.new_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="+ New Note",
            font=FONTS["card_title"],
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            height=34,
            command=self.create_new_note,
        )
        self.new_btn.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        # Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        self.search_entry = ctk.CTkEntry(
            self.sidebar_frame,
            placeholder_text="Search notes or #tags... (Ctrl+F)",
            textvariable=self.search_var,
            font=FONTS["body"],
            corner_radius=8,
            height=32,
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            border_color=self.theme["border"],
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        # Scrollable Note Cards
        self.cards_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            fg_color="transparent",
            corner_radius=0,
        )
        self.cards_scroll.grid(row=3, column=0, sticky="nsew", padx=6, pady=0)
        self.cards_scroll.grid_columnconfigure(0, weight=1)

        # Sidebar Footer: Tags filter container
        self.tags_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent", height=36)
        self.tags_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 12))

        # -------------------------------------------------------------
        # 2. Main Editor Area (Right Pane)
        # -------------------------------------------------------------
        self.editor_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=self.theme["bg_window"])
        self.editor_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.editor_frame.grid_rowconfigure(2, weight=1)
        self.editor_frame.grid_columnconfigure(0, weight=1)

        # Editor Header: Note Title + View Switcher + Action Buttons
        self.header_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent", height=48)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 6))
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.title_var = ctk.StringVar()
        self.title_var.trace_add("write", self._on_title_changed)
        self.title_entry = ctk.CTkEntry(
            self.header_frame,
            textvariable=self.title_var,
            font=FONTS["title"],
            border_width=0,
            fg_color="transparent",
            text_color=self.theme["text_primary"],
            placeholder_text="Untitled Note",
        )
        self.title_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=0)

        # View Mode Segmented Switcher
        self.view_switcher = ctk.CTkSegmentedButton(
            self.header_frame,
            values=["✍️ Edit", "👁️ Preview", "▦ Kanban"],
            font=("Segoe UI", 12),
            selected_color=self.theme["accent"],
            selected_hover_color=self.theme["accent_hover"],
            command=self._on_view_mode_changed,
        )
        self.view_switcher.set("✍️ Edit")
        self.view_switcher.grid(row=0, column=1, padx=(0, 12), pady=0)

        # Header Action Buttons
        self.pin_btn = ctk.CTkButton(
            self.header_frame,
            text="📌 Pin",
            font=FONTS["meta"],
            width=64,
            height=28,
            corner_radius=6,
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            hover_color=self.theme["bg_card_hover"],
            command=self.toggle_pin_active_note,
        )
        self.pin_btn.grid(row=0, column=2, padx=4, pady=0)

        self.del_btn = ctk.CTkButton(
            self.header_frame,
            text="🗑 Delete",
            font=FONTS["meta"],
            width=64,
            height=28,
            corner_radius=6,
            fg_color=self.theme["bg_card"],
            text_color="#EF4444",
            hover_color=self.theme["bg_card_hover"],
            command=self.delete_active_note,
        )
        self.del_btn.grid(row=0, column=3, padx=4, pady=0)

        # Metadata Bar (Date & Tag Badges)
        self.meta_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent", height=24)
        self.meta_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))

        self.meta_label = ctk.CTkLabel(
            self.meta_frame,
            text="",
            font=FONTS["meta"],
            text_color=self.theme["text_muted"],
        )
        self.meta_label.pack(side="left")

        # -------------------------------------------------------------
        # 3. Canvas Container (Switchable between Edit, Preview, Kanban)
        # -------------------------------------------------------------
        self.canvas_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        self.canvas_container.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 10))
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)

        # View A: Edit Mode Frame (Textbox + Checklists)
        self.edit_mode_frame = ctk.CTkFrame(self.canvas_container, fg_color="transparent")
        self.edit_mode_frame.grid_rowconfigure(0, weight=1)
        self.edit_mode_frame.grid_columnconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            self.edit_mode_frame,
            font=FONTS["body"],
            corner_radius=8,
            border_width=1,
            border_color=self.theme["border"],
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            wrap="word",
            undo=True,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 6))
        self.textbox.bind("<KeyRelease>", self._on_content_changed)

        self.tasks_container = ctk.CTkFrame(self.edit_mode_frame, fg_color="transparent", height=40)
        self.tasks_container.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 0))

        # View B: Rich Markdown Typography Preview Pane
        self.preview_pane = MarkdownPreviewPane(self.canvas_container, theme=self.theme)

        # View C: Embedded Kanban Board View
        self.kanban_pane = KanbanBoardView(
            self.canvas_container,
            theme=self.theme,
            on_task_toggled=self._on_kanban_task_toggled,
            on_add_task=self._on_kanban_add_task,
        )

        # Default visible view is Edit mode
        self.edit_mode_frame.grid(row=0, column=0, sticky="nsew")

        # Bottom Status Bar
        self.status_bar = ctk.CTkFrame(self.editor_frame, fg_color="transparent", height=30)
        self.status_bar.grid(row=4, column=0, sticky="ew", padx=24, pady=(4, 12))
        self.status_bar.grid_columnconfigure(1, weight=1)

        self.stats_label = ctk.CTkLabel(
            self.status_bar,
            text="0 words | 0 characters",
            font=FONTS["meta"],
            text_color=self.theme["text_muted"],
        )
        self.stats_label.grid(row=0, column=0, sticky="w")

        self.shortcuts_hint = ctk.CTkLabel(
            self.status_bar,
            text="Ctrl+K: Palette | Ctrl+N: New | Ctrl+S: Save",
            font=FONTS["meta"],
            text_color=self.theme["text_muted"],
        )
        self.shortcuts_hint.grid(row=0, column=1, sticky="w", padx=24)

        self.save_status = ctk.CTkLabel(
            self.status_bar,
            text="● Saved",
            font=FONTS["meta"],
            text_color="#10B981",
        )
        self.save_status.grid(row=0, column=2, padx=12)

        self.theme_btn = ctk.CTkButton(
            self.status_bar,
            text="Theme: Dark" if self.current_theme_name == "dark" else "Theme: Warm",
            font=FONTS["meta"],
            width=90,
            height=24,
            corner_radius=6,
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            command=self.toggle_theme,
        )
        self.theme_btn.grid(row=0, column=3, sticky="e")

    # -------------------------------------------------------------
    # Multi-View Management (Edit / Preview / Kanban)
    # -------------------------------------------------------------
    def _on_view_mode_changed(self, mode: str):
        self._set_view_mode(mode)

    def _set_view_mode(self, mode: str):
        # Save active modifications before switching views
        if self.current_view_mode == "✍️ Edit":
            self._save_active_note_now()

        self.current_view_mode = mode
        self.view_switcher.set(mode)

        # Hide all panes first
        self.edit_mode_frame.grid_forget()
        self.preview_pane.grid_forget()
        self.kanban_pane.grid_forget()

        if mode == "✍️ Edit":
            self.edit_mode_frame.grid(row=0, column=0, sticky="nsew")
            self.textbox.focus()
        elif mode == "👁️ Preview":
            self.preview_pane.grid(row=0, column=0, sticky="nsew")
            content = self.textbox.get("1.0", "end-1c") if self.active_note else ""
            self.preview_pane.render_markdown(content)
        elif mode == "▦ Kanban":
            self.kanban_pane.grid(row=0, column=0, sticky="nsew")
            if self.active_note:
                self.kanban_pane.load_note(self.active_note)

    def _on_kanban_task_toggled(self, task_text: str, is_done: bool):
        if not self.active_note:
            return
        toggled, updated = TaskEngine.toggle_task(self.active_note, task_text, target_state=is_done, storage=self.storage)
        if toggled:
            self.active_note = updated
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", updated.content)
            self.kanban_pane.load_note(updated)
            self._render_interactive_tasks()
            self._render_cards()

    def _on_kanban_add_task(self, task_text: str):
        if not self.active_note:
            return
        new_content = f"{self.active_note.content.rstrip()}\n- [ ] {task_text}\n"
        self.active_note.content = new_content
        self.storage.write_note(self.active_note)
        self.indexer.index_note(self.active_note)
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", new_content)
        self.kanban_pane.load_note(self.active_note)
        self._render_interactive_tasks()
        self._render_cards()

    # -------------------------------------------------------------
    # Command Palette Integration
    # -------------------------------------------------------------
    def open_command_palette(self, event=None):
        """Open floating spotlight command palette."""
        modal = CommandPaletteModal(
            parent=self,
            theme=self.theme,
            notes=self.notes,
            on_select_note=self.select_note,
            on_action=self._handle_palette_action,
        )

    def _handle_palette_action(self, action_key: str):
        if action_key == "new_note":
            self.create_new_note()
        elif action_key == "toggle_pin":
            self.toggle_pin_active_note()
        elif action_key == "toggle_kanban":
            target = "✍️ Edit" if self.current_view_mode == "▦ Kanban" else "▦ Kanban"
            self._set_view_mode(target)
        elif action_key == "toggle_preview":
            target = "✍️ Edit" if self.current_view_mode == "👁️ Preview" else "👁️ Preview"
            self._set_view_mode(target)
        elif action_key == "toggle_theme":
            self.toggle_theme()

    # -------------------------------------------------------------
    # Note Management & Card Rendering
    # -------------------------------------------------------------
    def refresh_notes_list(self):
        """Fetch notes from disk/indexer and render cards."""
        self.indexer.sync_from_storage(self.storage)
        all_notes = self.storage.list_notes()

        # Apply search and tag filters
        filtered = all_notes
        if self.selected_tag:
            filtered = [n for n in filtered if self.selected_tag in n.tags]
        if self.search_query.strip():
            filtered = MultiTokenSearch.rank_notes(filtered, self.search_query)

        self.notes = filtered
        self._render_cards()
        self._render_tags_bar()

    def _render_cards(self):
        """Re-render high-end note cards in the scrollable sidebar."""
        for widget in self.cards_scroll.winfo_children():
            widget.destroy()

        if not self.notes:
            empty_lbl = ctk.CTkLabel(
                self.cards_scroll,
                text="No notes found.",
                font=FONTS["meta"],
                text_color=self.theme["text_muted"],
            )
            empty_lbl.pack(pady=20)
            return

        for note in self.notes:
            is_active = self.active_note and self.active_note.id == note.id
            card = NoteCard(
                master=self.cards_scroll,
                note=note,
                is_active=bool(is_active),
                theme=self.theme,
                on_click=self.select_note,
                on_pin_toggle=self.toggle_pin_note,
                on_duplicate=self.duplicate_note,
                on_delete=self.delete_note,
                on_export=self.export_note,
            )
            card.pack(fill="x", pady=4, padx=4)

    def _render_tags_bar(self):
        """Render horizontal clickable tag chips at bottom of sidebar."""
        for widget in self.tags_frame.winfo_children():
            widget.destroy()

        all_tags = self.indexer.get_all_tags()
        if not all_tags:
            return

        all_btn = ctk.CTkButton(
            self.tags_frame,
            text="All",
            width=40,
            height=22,
            font=FONTS["meta"],
            fg_color=self.theme["accent"] if not self.selected_tag else self.theme["bg_card"],
            text_color="#FFFFFF" if not self.selected_tag else self.theme["text_primary"],
            command=lambda: self._select_tag_filter(None),
        )
        all_btn.pack(side="left", padx=2)

        for tag_info in all_tags[:4]:
            t = tag_info["tag"]
            is_sel = self.selected_tag == t
            btn = ctk.CTkButton(
                self.tags_frame,
                text=f"#{t}",
                width=50,
                height=22,
                font=FONTS["meta"],
                fg_color=self.theme["accent"] if is_sel else self.theme["bg_card"],
                text_color="#FFFFFF" if is_sel else self.theme["text_primary"],
                command=lambda tag=t: self._select_tag_filter(tag),
            )
            btn.pack(side="left", padx=2)

    def _select_tag_filter(self, tag: Optional[str]):
        self.selected_tag = None if self.selected_tag == tag else tag
        self.refresh_notes_list()

    def select_note(self, note: Note):
        """Load note into editor and sync all open view canvases."""
        if self.active_note and self.active_note.id != note.id:
            self._save_active_note_now()

        fresh = self.storage.get_note(note.id) or note
        self.active_note = fresh

        self.title_var.set(fresh.title)
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", fresh.content)

        updated_fmt = fresh.updated_at[:16].replace("T", " ")
        tags_fmt = " ".join([f"#{t}" for t in fresh.tags])
        self.meta_label.configure(text=f"Updated: {updated_fmt}  {tags_fmt}")
        self.pin_btn.configure(text="📌 Unpin" if fresh.is_pinned else "📌 Pin")

        self._update_stats()
        self._render_interactive_tasks()
        self._render_cards()

        # Update preview or kanban if currently active
        if self.current_view_mode == "👁️ Preview":
            self.preview_pane.render_markdown(fresh.content)
        elif self.current_view_mode == "▦ Kanban":
            self.kanban_pane.load_note(fresh)

    def create_new_note(self):
        """Create a fresh note and focus editor."""
        if self.active_note:
            self._save_active_note_now()

        note = self.storage.create_note(title="Untitled Note", content="# Untitled Note\n\nStart typing your calm notes here...")
        self.indexer.index_note(note)
        self.refresh_notes_list()
        self.select_note(note)
        if self.current_view_mode != "✍️ Edit":
            self._set_view_mode("✍️ Edit")
        self.title_entry.focus()
        self.title_entry.select_range(0, "end")

    def delete_note(self, note: Note):
        """Soft-delete specified note."""
        deleted_id = note.id
        self.storage.delete_note(deleted_id)
        self.indexer.remove_note(deleted_id)
        if self.active_note and self.active_note.id == deleted_id:
            self.active_note = None

        self.refresh_notes_list()
        if self.notes:
            self.select_note(self.notes[0])
        else:
            self.create_new_note()

    def delete_active_note(self):
        """Soft-delete current active note."""
        if self.active_note:
            self.delete_note(self.active_note)

    def toggle_pin_note(self, note: Note):
        note.is_pinned = not note.is_pinned
        self.storage.write_note(note)
        self.indexer.index_note(note)
        if self.active_note and self.active_note.id == note.id:
            self.pin_btn.configure(text="📌 Unpin" if note.is_pinned else "📌 Pin")
        self.refresh_notes_list()

    def toggle_pin_active_note(self):
        if self.active_note:
            self.toggle_pin_note(self.active_note)

    def duplicate_note(self, note: Note):
        """Clone an existing note with clean slug and timestamp."""
        cloned = self.storage.duplicate_note(note.id)
        if cloned:
            self.indexer.index_note(cloned)
            self.refresh_notes_list()
            self.select_note(cloned)

    def export_note(self, note: Note, fmt: str):
        """Export note to Markdown or clean standalone HTML."""
        if fmt == "html":
            dest = filedialog.asksaveasfilename(
                title="Export Note as HTML",
                defaultextension=".html",
                filetypes=[("HTML Document", "*.html"), ("All Files", "*.*")],
                initialfile=f"{note.slug}.html",
            )
            if dest:
                out_path = self.storage.export_as_html(note, Path(dest))
                messagebox.showinfo("Export Complete", f"Exported HTML to:\n{out_path}")
        elif fmt == "md":
            dest = filedialog.asksaveasfilename(
                title="Export Note as Markdown",
                defaultextension=".md",
                filetypes=[("Markdown Document", "*.md"), ("All Files", "*.*")],
                initialfile=f"{note.slug}.md",
            )
            if dest:
                Path(dest).write_text(note.content, encoding="utf-8")
                messagebox.showinfo("Export Complete", f"Exported Markdown to:\n{dest}")

    # -------------------------------------------------------------
    # Real-time Auto-save & Checklist Interactivity
    # -------------------------------------------------------------
    def _on_content_changed(self, event=None):
        self.save_status.configure(text="● Editing...", text_color="#F59E0B")
        self._update_stats()

        if self.auto_save_job:
            self.after_cancel(self.auto_save_job)
        self.auto_save_job = self.after(self.config.auto_save_delay_ms, self._save_active_note_now)

    def _on_title_changed(self, *args):
        if not self.active_note:
            return
        new_title = self.title_var.get().strip()
        if new_title and new_title != self.active_note.title:
            self.active_note.title = new_title
            if self.auto_save_job:
                self.after_cancel(self.auto_save_job)
            self.auto_save_job = self.after(self.config.auto_save_delay_ms, self._save_active_note_now)

    def _save_active_note_now(self):
        if not self.active_note:
            return

        current_text = self.textbox.get("1.0", "end-1c")
        current_title = self.title_var.get().strip() or "Untitled Note"

        prev_content = self.active_note.content
        self.active_note.title = current_title
        self.active_note.content = current_text
        self.active_note.tags = self.storage.extract_tags(current_text)

        # Record history diff snapshot
        self.history.record_snapshot(self.active_note, prev_content=prev_content)

        # Atomic write to disk
        self.storage.write_note(self.active_note)
        self.indexer.index_note(self.active_note)

        self.save_status.configure(text="● Saved", text_color="#10B981")
        self._render_interactive_tasks()
        self._render_cards()

    def _render_interactive_tasks(self):
        """Extract - [ ] checklist items and display clickable checkboxes below editor."""
        for w in self.tasks_container.winfo_children():
            w.destroy()

        if not self.active_note:
            return

        tasks = TaskEngine.extract_tasks_from_note(self.active_note)
        if not tasks:
            return

        tasks_header = ctk.CTkLabel(
            self.tasks_container,
            text=f"Checklists ({len(tasks)}):",
            font=FONTS["card_title"],
            text_color=self.theme["text_primary"],
        )
        tasks_header.pack(anchor="w", pady=(4, 2))

        for task in tasks[:5]:
            cb_var = ctk.BooleanVar(value=task.is_done)
            cb = ctk.CTkCheckBox(
                self.tasks_container,
                text=task.text,
                variable=cb_var,
                font=FONTS["body"],
                text_color=self.theme["text_muted"] if task.is_done else self.theme["text_primary"],
                fg_color=self.theme["accent"],
                command=lambda t=task.text, v=cb_var: self._on_checkbox_toggled(t, v.get()),
            )
            cb.pack(anchor="w", pady=2)

    def _on_checkbox_toggled(self, task_text: str, is_done: bool):
        if not self.active_note:
            return
        toggled, updated = TaskEngine.toggle_task(self.active_note, task_text, target_state=is_done, storage=self.storage)
        if toggled:
            self.active_note = updated
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", updated.content)
            self._render_interactive_tasks()
            self._render_cards()

    def _update_stats(self):
        text = self.textbox.get("1.0", "end-1c")
        chars = len(text)
        words = len(text.split())
        self.stats_label.configure(text=f"{words} words | {chars} characters")

    def _on_search_changed(self, *args):
        self.search_query = self.search_var.get()
        self.refresh_notes_list()

    def toggle_theme(self):
        """Toggle between Warm Paper and Dark Zen palettes."""
        self.current_theme_name = "warm" if self.current_theme_name == "dark" else "dark"
        self.config.theme = self.current_theme_name
        self.config.save_to_file()
        self.theme = THEMES[self.current_theme_name]
        ctk.set_appearance_mode(self.theme["appearance_mode"])
        self.theme_btn.configure(text=f"Theme: {self.current_theme_name.capitalize()}")
        # Rebuild layout to apply new theme tokens
        for w in self.winfo_children():
            w.destroy()
        self._build_layout()
        self._setup_global_shortcuts()
        self.refresh_notes_list()
        if self.active_note:
            self.select_note(self.active_note)

    def _poll_disk_changes(self):
        """Check for external disk updates (from CLI or AI agents) and refresh gently."""
        try:
            mtime_sum = sum(p.stat().st_mtime for p in self.config.notes_dir.glob("*.md") if p.is_file())
            if self.last_sync_mtime > 0 and mtime_sum != self.last_sync_mtime:
                # Disk modified externally
                self.indexer.sync_from_storage(self.storage)
                self.refresh_notes_list()
                if self.active_note:
                    fresh = self.storage.get_note(self.active_note.id)
                    if fresh and fresh.content != self.textbox.get("1.0", "end-1c"):
                        self.textbox.delete("1.0", "end")
                        self.textbox.insert("1.0", fresh.content)
                        if self.current_view_mode == "👁️ Preview":
                            self.preview_pane.render_markdown(fresh.content)
                        elif self.current_view_mode == "▦ Kanban":
                            self.kanban_pane.load_note(fresh)
            self.last_sync_mtime = mtime_sum
        except Exception:
            pass
        self.after(2000, self._poll_disk_changes)


def run_gui() -> int:
    """Entry point for native desktop GUI application."""
    app = LunarDesktopApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    run_gui()
