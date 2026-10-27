import customtkinter as ctk
from typing import Dict, Any, Callable, Optional
from lunariz.core.storage import Note, NoteStorage
from lunariz.core.tasks import TaskEngine, TaskItem


class KanbanBoardView(ctk.CTkFrame):
    """Interactive visual Kanban board embedded directly in the Desktop GUI."""

    def __init__(self, master, theme: Dict[str, Any], on_task_toggled: Callable[[str, bool], None], on_add_task: Callable[[str], None], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.theme = theme
        self.on_task_toggled = on_task_toggled
        self.on_add_task = on_add_task
        self.active_note: Optional[Note] = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header controls
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent", height=36)
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(4, 10))
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.add_entry = ctk.CTkEntry(
            self.top_bar,
            placeholder_text="Enter new task description...",
            font=("Segoe UI", 12),
            height=30,
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            border_color=self.theme["border"],
        )
        self.add_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.add_entry.bind("<Return>", lambda e: self._submit_new_task())

        self.add_btn = ctk.CTkButton(
            self.top_bar,
            text="+ Add Task",
            font=("Segoe UI", 12, "bold"),
            width=90,
            height=30,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            command=self._submit_new_task,
        )
        self.add_btn.grid(row=0, column=1)

        # Columns scroll area
        self.board_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", orientation="horizontal")
        self.board_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=0)

    def _submit_new_task(self):
        text = self.add_entry.get().strip()
        if text and self.on_add_task:
            self.on_add_task(text)
            self.add_entry.delete(0, "end")

    def render_board(self, note: Optional[Note]):
        """Parse tasks and render visual Kanban columns."""
        self.active_note = note

        # Clear existing columns
        for w in self.board_scroll.winfo_children():
            w.destroy()

        if not note:
            empty_lbl = ctk.CTkLabel(
                self.board_scroll,
                text="No note selected. Select a note with tasks (- [ ]) to view Kanban.",
                font=("Segoe UI", 13),
                text_color=self.theme["text_muted"],
            )
            empty_lbl.pack(padx=30, pady=40)
            return

        columns_data = TaskEngine.project_kanban(note)
        if not columns_data or all(len(tasks) == 0 for tasks in columns_data.values()):
            empty_lbl = ctk.CTkLabel(
                self.board_scroll,
                text="No checklist tasks found in this note. Add tasks using '- [ ] Task name' or the input above.",
                font=("Segoe UI", 13),
                text_color=self.theme["text_muted"],
            )
            empty_lbl.pack(padx=30, pady=40)
            return

        for col_name, tasks in columns_data.items():
            self._render_column(col_name, tasks)

    def _render_column(self, title: str, tasks: list[TaskItem]):
        """Render an individual Kanban column with task cards."""
        col_frame = ctk.CTkFrame(
            self.board_scroll,
            width=280,
            fg_color=self.theme["bg_sidebar"],
            corner_radius=8,
            border_width=1,
            border_color=self.theme["border"],
        )
        col_frame.pack(side="left", fill="y", padx=8, pady=4)
        col_frame.pack_propagate(False)

        # Column Header Badge
        header_color = self.theme["accent"] if "pending" in title.lower() or "to do" in title.lower() else "#10B981"
        header = ctk.CTkFrame(col_frame, fg_color="transparent", height=32)
        header.pack(fill="x", padx=10, pady=(10, 6))

        title_lbl = ctk.CTkLabel(
            header,
            text=f"{title} ({len(tasks)})",
            font=("Segoe UI", 13, "bold"),
            text_color=header_color,
        )
        title_lbl.pack(side="left")

        # Cards container
        cards_box = ctk.CTkScrollableFrame(col_frame, fg_color="transparent")
        cards_box.pack(fill="both", expand=True, padx=6, pady=4)

        for task in tasks:
            card = ctk.CTkFrame(
                cards_box,
                fg_color=self.theme["bg_card"],
                corner_radius=6,
                border_width=1,
                border_color=self.theme["border"],
            )
            card.pack(fill="x", pady=4, padx=2)

            task_lbl = ctk.CTkLabel(
                card,
                text=task.text,
                font=("Segoe UI", 12),
                text_color=self.theme["text_muted"] if task.is_done else self.theme["text_primary"],
                wraplength=220,
                justify="left",
                anchor="w",
            )
            task_lbl.pack(fill="x", padx=10, pady=(8, 4))

            # Action button to flip state
            action_btn = ctk.CTkButton(
                card,
                text="Reopen ○" if task.is_done else "Done ✔",
                width=65,
                height=22,
                font=("Segoe UI", 10),
                fg_color=self.theme["tag_bg"],
                text_color=self.theme["accent"],
                hover_color=self.theme["border"],
                command=lambda t=task.text, s=task.is_done: self.on_task_toggled(t, not s),
            )
            action_btn.pack(anchor="e", padx=8, pady=(0, 6))
