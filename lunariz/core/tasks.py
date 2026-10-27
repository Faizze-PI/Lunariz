import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from lunariz.core.storage import Note, NoteStorage


@dataclass
class TaskItem:
    note_id: str
    note_title: str
    text: str
    is_done: bool
    line_num: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "note_title": self.note_title,
            "text": self.text,
            "is_done": self.is_done,
            "line_num": self.line_num,
        }


class TaskEngine:
    TASK_REGEX = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$")

    @classmethod
    def extract_tasks_from_content(cls, content: str, note_id: str = "", note_title: str = "") -> List[TaskItem]:
        """Parse all GFM checklist items from note content."""
        tasks = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            match = cls.TASK_REGEX.match(line)
            if match:
                is_done = match.group(2).lower() == "x"
                task_text = match.group(3).strip()
                tasks.append(TaskItem(
                    note_id=note_id,
                    note_title=note_title,
                    text=task_text,
                    is_done=is_done,
                    line_num=line_num,
                ))
        return tasks

    @classmethod
    def extract_tasks_from_note(cls, note: Note) -> List[TaskItem]:
        """Extract tasks from a Note object."""
        return cls.extract_tasks_from_content(note.content, note.id, note.title)

    @classmethod
    def toggle_task(
        cls,
        note: Note,
        task_query: str,
        target_state: Optional[bool] = None,
        storage: Optional[NoteStorage] = None,
    ) -> Tuple[bool, Note]:
        """
        Locate matching task text in note content, flip [ ] <-> [x],
        and optionally write back to disk atomically.
        """
        lines = note.content.splitlines()
        modified = False
        target_q = task_query.strip().lower()

        new_lines = []
        for line in lines:
            match = cls.TASK_REGEX.match(line)
            if match and not modified:
                indent = match.group(1)
                mark = match.group(2)
                text = match.group(3)

                if target_q in text.lower():
                    is_done = mark.lower() == "x"
                    new_done = not is_done if target_state is None else target_state
                    new_mark = "x" if new_done else " "
                    line = f"{indent}- [{new_mark}] {text}"
                    modified = True

            new_lines.append(line)

        if modified:
            note.content = "\n".join(new_lines)
            if storage:
                note = storage.write_note(note)

        return modified, note

    @classmethod
    def project_kanban(cls, note: Note) -> Dict[str, List[TaskItem]]:
        """Project note tasks into Kanban columns based on headers or completion."""
        lines = note.content.splitlines()
        columns: Dict[str, List[TaskItem]] = {}
        current_col = "To Do"

        has_custom_headers = any(line.strip().startswith("## ") for line in lines)

        if has_custom_headers:
            for line_num, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("## "):
                    current_col = stripped.lstrip("#").strip()
                    if current_col not in columns:
                        columns[current_col] = []
                    continue

                match = cls.TASK_REGEX.match(line)
                if match:
                    if current_col not in columns:
                        columns[current_col] = []
                    is_done = match.group(2).lower() == "x"
                    columns[current_col].append(TaskItem(
                        note_id=note.id,
                        note_title=note.title,
                        text=match.group(3).strip(),
                        is_done=is_done,
                        line_num=line_num,
                    ))
        else:
            # Group into standard Backlog / Done
            columns = {"Pending": [], "Completed": []}
            for task in cls.extract_tasks_from_note(note):
                if task.is_done:
                    columns["Completed"].append(task)
                else:
                    columns["Pending"].append(task)

        return columns
