import customtkinter as ctk
from typing import Dict, Any, Callable, List, Optional
from lunariz.core.storage import Note


class CommandPaletteModal(ctk.CTkToplevel):
    """Floating Spotlight/Command Palette modal (Ctrl+K) for instant keyboard navigation."""

    def __init__(
        self,
        parent,
        theme: Dict[str, Any],
        notes: List[Note],
        on_select_note: Callable[[Note], None],
        on_action: Callable[[str], None],
    ):
        super().__init__(parent)
        self.theme = theme
        self.all_notes = notes
        self.on_select_note = on_select_note
        self.on_action = on_action

        # Modal window properties
        self.title("Command Palette")
        self.geometry("560x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent window
        self._center_window(parent)

        self.configure(fg_color=self.theme["bg_window"])

        # Grid setup
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_filter)
        self.search_entry = ctk.CTkEntry(
            self,
            textvariable=self.search_var,
            placeholder_text="Type a command or note name...",
            font=("Segoe UI", 14),
            height=40,
            corner_radius=8,
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            border_color=self.theme["accent"],
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        self.search_entry.focus()

        # Results scroll area
        self.results_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        # Keyboard navigation
        self.bind("<Escape>", lambda e: self.destroy())

        # Render initial commands and notes
        self._render_items("")

    def _center_window(self, parent):
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 560
        h = 420
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_filter(self, *args):
        self._render_items(self.search_var.get().strip().lower())

    def _render_items(self, query: str):
        for w in self.results_scroll.winfo_children():
            w.destroy()

        # Base commands
        commands = [
            ("⚡ Action: Create New Note", "new_note"),
            ("📌 Action: Toggle Pin Status", "toggle_pin"),
            ("▦ Action: Toggle Kanban Board View", "toggle_kanban"),
            ("👁️ Action: Toggle Markdown Preview", "toggle_preview"),
            ("🌓 Action: Toggle Theme (Dark / Warm)", "toggle_theme"),
        ]

        # Filter commands
        matching_cmds = [c for c in commands if query in c[0].lower()]
        for label, action_key in matching_cmds:
            btn = ctk.CTkButton(
                self.results_scroll,
                text=label,
                font=("Segoe UI", 12, "bold"),
                anchor="w",
                fg_color=self.theme["bg_card"],
                text_color=self.theme["accent"],
                hover_color=self.theme["bg_card_hover"],
                corner_radius=6,
                height=32,
                command=lambda act=action_key: self._exec_action(act),
            )
            btn.pack(fill="x", pady=2)

        # Filter notes
        matching_notes = [n for n in self.all_notes if query in n.title.lower() or query in n.snippet.lower()]
        for note in matching_notes[:15]:
            note_btn = ctk.CTkButton(
                self.results_scroll,
                text=f"📝 {note.title}  —  {note.snippet[:50]}",
                font=("Segoe UI", 12),
                anchor="w",
                fg_color=self.theme["bg_card"],
                text_color=self.theme["text_primary"],
                hover_color=self.theme["bg_card_hover"],
                corner_radius=6,
                height=32,
                command=lambda n=note: self._exec_note(n),
            )
            note_btn.pack(fill="x", pady=2)

    def _exec_action(self, action_key: str):
        self.destroy()
        self.on_action(action_key)

    def _exec_note(self, note: Note):
        self.destroy()
        self.on_select_note(note)
