import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Dict, Any, Callable
from lunariz.core.storage import Note
from lunariz.gui.theme import FONTS, format_relative_time, sanitize_snippet


class NoteCard(ctk.CTkFrame):
    """High-end note card with active accent borders, relative time, and right-click context menu."""

    def __init__(
        self,
        master,
        note: Note,
        is_active: bool,
        theme: Dict[str, Any],
        on_click: Callable[[Note], None],
        on_pin_toggle: Callable[[Note], None],
        on_duplicate: Callable[[Note], None],
        on_delete: Callable[[Note], None],
        on_export: Callable[[Note, str], None],
        **kwargs,
    ):
        card_bg = theme["bg_card_selected"] if is_active else theme["bg_card"]
        border_color = theme["accent"] if is_active else theme["border"]
        border_width = 2 if is_active else 1

        super().__init__(
            master,
            fg_color=card_bg,
            corner_radius=8,
            border_width=border_width,
            border_color=border_color,
            cursor="hand2",
            **kwargs,
        )

        self.note = note
        self.is_active = is_active
        self.theme = theme
        self.on_click = on_click
        self.on_pin_toggle = on_pin_toggle
        self.on_duplicate = on_duplicate
        self.on_delete = on_delete
        self.on_export = on_export

        self._build_card()
        self._setup_bindings()
        self._setup_context_menu()

    def _build_card(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # Header: Title + Relative Timestamp
        header_text = f"📌 {self.note.title}" if self.note.is_pinned else self.note.title
        self.title_lbl = ctk.CTkLabel(
            self,
            text=header_text,
            font=FONTS["card_title"],
            text_color=self.theme["text_primary"],
            anchor="w",
        )
        self.title_lbl.grid(row=0, column=0, sticky="w", padx=(12, 4), pady=(8, 2))

        # Relative time badge
        rel_time = format_relative_time(self.note.updated_at)
        self.time_lbl = ctk.CTkLabel(
            self,
            text=rel_time,
            font=FONTS["meta"],
            text_color=self.theme["text_muted"],
            anchor="e",
        )
        self.time_lbl.grid(row=0, column=1, sticky="e", padx=(4, 12), pady=(8, 2))

        # Clean snippet preview
        snippet_text = sanitize_snippet(self.note.content)
        self.snippet_lbl = ctk.CTkLabel(
            self,
            text=snippet_text,
            font=FONTS["snippet"],
            text_color=self.theme["text_muted"],
            anchor="w",
            wraplength=230,
            justify="left",
        )
        self.snippet_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4))

        # Tag pills
        if self.note.tags:
            tags_str = " ".join([f"#{t}" for t in self.note.tags[:3]])
            self.tag_lbl = ctk.CTkLabel(
                self,
                text=tags_str,
                font=FONTS["meta"],
                text_color=self.theme["tag_fg"],
                anchor="w",
            )
            self.tag_lbl.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

    def _setup_bindings(self):
        """Click and hover interaction hooks."""
        widgets = [self, self.title_lbl, self.time_lbl, self.snippet_lbl]
        if hasattr(self, "tag_lbl"):
            widgets.append(self.tag_lbl)

        for w in widgets:
            w.bind("<Button-1>", lambda e: self.on_click(self.note))
            w.bind("<Enter>", lambda e: self._on_hover(True))
            w.bind("<Leave>", lambda e: self._on_hover(False))

    def _on_hover(self, is_hover: bool):
        if not self.is_active:
            new_bg = self.theme["bg_card_hover"] if is_hover else self.theme["bg_card"]
            self.configure(fg_color=new_bg)

    def _setup_context_menu(self):
        """Right-click action menu."""
        self.menu = tk.Menu(
            self,
            tearoff=0,
            bg=self.theme["bg_card"],
            fg=self.theme["text_primary"],
            activebackground=self.theme["accent"],
            activeforeground="#FFFFFF",
            bd=1,
            relief="solid",
        )
        pin_label = "📌 Unpin Note" if self.note.is_pinned else "📌 Pin Note"
        self.menu.add_command(label=pin_label, command=lambda: self.on_pin_toggle(self.note))
        self.menu.add_command(label="📋 Duplicate Note", command=lambda: self.on_duplicate(self.note))
        self.menu.add_command(label="📁 Copy File Path", command=self._copy_path)
        self.menu.add_separator()
        self.menu.add_command(label="📤 Export as Markdown...", command=lambda: self.on_export(self.note, "md"))
        self.menu.add_command(label="🌐 Export as Clean HTML...", command=lambda: self.on_export(self.note, "html"))
        self.menu.add_separator()
        self.menu.add_command(label="🗑 Delete Note", command=lambda: self.on_delete(self.note), foreground="#EF4444")

        # Bind right-click on Windows (<Button-3>) and macOS (<Button-2>)
        widgets = [self, self.title_lbl, self.time_lbl, self.snippet_lbl]
        if hasattr(self, "tag_lbl"):
            widgets.append(self.tag_lbl)

        for w in widgets:
            w.bind("<Button-3>", self._show_context_menu)
            w.bind("<Button-2>", self._show_context_menu)

    def _show_context_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _copy_path(self):
        self.clipboard_clear()
        self.clipboard_append(str(self.note.path))
