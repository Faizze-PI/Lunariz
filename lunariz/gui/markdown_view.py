import re
import customtkinter as ctk
from typing import Dict, Any


class MarkdownPreviewPane(ctk.CTkFrame):
    """Calm rendered Markdown preview pane with formatted typography and code blocks."""

    def __init__(self, master, theme: Dict[str, Any], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.theme = theme

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            self,
            font=("Segoe UI", 13),
            corner_radius=8,
            border_width=1,
            border_color=self.theme["border"],
            fg_color=self.theme["bg_card"],
            text_color=self.theme["text_primary"],
            wrap="word",
            activate_scrollbars=True,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Configure Tk text tags for Markdown styling
        self._setup_tags()

    def _setup_tags(self):
        """Set up styling tags inside the underlying Tkinter text widget."""
        tk_text = self.textbox._textbox

        tk_text.tag_configure("h1", font=("Segoe UI", 20, "bold"), foreground=self.theme["text_primary"], spacing3=10)
        tk_text.tag_configure("h2", font=("Segoe UI", 16, "bold"), foreground=self.theme["text_primary"], spacing3=8)
        tk_text.tag_configure("h3", font=("Segoe UI", 14, "bold"), foreground=self.theme["text_primary"], spacing3=6)
        tk_text.tag_configure("bold", font=("Segoe UI", 13, "bold"), foreground=self.theme["text_primary"])
        tk_text.tag_configure("italic", font=("Segoe UI", 13, "italic"), foreground=self.theme["text_primary"])
        tk_text.tag_configure("code_inline", font=("Cascadia Code", 11), background=self.theme["tag_bg"], foreground=self.theme["accent"])
        tk_text.tag_configure("code_block", font=("Cascadia Code", 11), background=self.theme["tag_bg"], foreground=self.theme["text_primary"], lmargin1=15, lmargin2=15)
        tk_text.tag_configure("blockquote", font=("Georgia", 13, "italic"), foreground=self.theme["text_muted"], lmargin1=20, lmargin2=20)
        tk_text.tag_configure("tag_pill", font=("Segoe UI", 11, "bold"), foreground=self.theme["tag_fg"])
        tk_text.tag_configure("task_done", font=("Segoe UI", 13), foreground=self.theme["text_muted"])
        tk_text.tag_configure("task_pending", font=("Segoe UI", 13), foreground=self.theme["text_primary"])

    def render_markdown(self, raw_content: str):
        """Parse and render markdown text with visual formatting tags."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")

        tk_text = self.textbox._textbox
        lines = raw_content.splitlines()

        in_code_block = False

        for line in lines:
            # Code fence toggle
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                tk_text.insert("end", line + "\n", "code_block")
                continue

            # Headers
            if line.startswith("# "):
                tk_text.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                tk_text.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("### "):
                tk_text.insert("end", line[4:] + "\n", "h3")
            # Blockquotes
            elif line.startswith("> "):
                tk_text.insert("end", "▎ " + line[2:] + "\n", "blockquote")
            # Tasks
            elif re.match(r"^\s*[-*+]\s+\[x\]\s+", line, re.IGNORECASE):
                task_txt = re.sub(r"^\s*[-*+]\s+\[x\]\s+", "", line, flags=re.IGNORECASE)
                tk_text.insert("end", "✔  " + task_txt + "\n", "task_done")
            elif re.match(r"^\s*[-*+]\s+\[ \]\s+", line):
                task_txt = re.sub(r"^\s*[-*+]\s+\[ \]\s+", "", line)
                tk_text.insert("end", "○  " + task_txt + "\n", "task_pending")
            # Unordered lists
            elif line.strip().startswith("- ") or line.strip().startswith("* "):
                clean_item = "•  " + line.strip()[2:]
                self._insert_inline_formatted(tk_text, clean_item + "\n")
            else:
                self._insert_inline_formatted(tk_text, line + "\n")

        self.textbox.configure(state="disabled")

    def _insert_inline_formatted(self, tk_text, line: str):
        """Apply bold, inline code, and tag highlights to a paragraph line."""
        # Simple inline parser for **bold**, `code`, and #tags
        tokens = re.split(r"(\*\*.*?\*\*|`.*?`|#\w+)", line)
        for tok in tokens:
            if tok.startswith("**") and tok.endswith("**"):
                tk_text.insert("end", tok[2:-2], "bold")
            elif tok.startswith("`") and tok.endswith("`"):
                tk_text.insert("end", " " + tok[1:-1] + " ", "code_inline")
            elif tok.startswith("#") and len(tok) > 1 and not tok.startswith("##"):
                tk_text.insert("end", tok, "tag_pill")
            else:
                tk_text.insert("end", tok)
