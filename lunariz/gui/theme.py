"""Calm design themes, typography tokens, and time formatting helpers."""

from datetime import datetime, timezone


THEMES = {
    "dark": {
        "appearance_mode": "Dark",
        "bg_window": "#161614",
        "bg_sidebar": "#121210",
        "bg_card": "#1E1E1B",
        "bg_card_selected": "#282824",
        "bg_card_hover": "#22221F",
        "text_primary": "#E6E4DE",
        "text_muted": "#8A8780",
        "accent": "#818CF8",
        "accent_hover": "#6366F1",
        "border": "#2A2A26",
        "tag_bg": "#222220",
        "tag_fg": "#A5B4FC",
        "pin_fg": "#FBBF24",
        "col_pending": "#F59E0B",
        "col_progress": "#3B82F6",
        "col_done": "#10B981",
    },
    "warm": {
        "appearance_mode": "Light",
        "bg_window": "#FBF9F5",
        "bg_sidebar": "#F4EFE6",
        "bg_card": "#FFFFFF",
        "bg_card_selected": "#EFE9DF",
        "bg_card_hover": "#F8F5EE",
        "text_primary": "#282725",
        "text_muted": "#7D7A75",
        "accent": "#B45309",
        "accent_hover": "#92400E",
        "border": "#E6DFD5",
        "tag_bg": "#EFE8DC",
        "tag_fg": "#B45309",
        "pin_fg": "#D97706",
        "col_pending": "#D97706",
        "col_progress": "#2563EB",
        "col_done": "#059669",
    },
}

FONTS = {
    "title": ("Segoe UI", 18, "bold"),
    "header": ("Segoe UI", 14, "bold"),
    "card_title": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 13),
    "snippet": ("Segoe UI", 11),
    "meta": ("Segoe UI", 10),
    "tag": ("Segoe UI", 10, "bold"),
    "code": ("Cascadia Code", 11),
}


def format_relative_time(iso_str: str) -> str:
    """Format an ISO timestamp into a human-readable relative string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (now - dt).total_seconds()

        if diff < 60:
            return "Just now"
        elif diff < 3600:
            mins = max(1, int(diff // 60))
            return f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff // 3600)
            return f"{hours}h ago"
        elif diff < 172800:
            return "Yesterday"
        elif diff < 604800:
            days = int(diff // 86400)
            return f"{days}d ago"
        else:
            return dt.strftime("%b %d")
    except Exception:
        return iso_str[:10]


def sanitize_snippet(content: str, max_chars: int = 90) -> str:
    """Clean markdown artifacts for a distraction-free card preview snippet."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "Empty note..."

    # Skip header title line
    if lines and lines[0].startswith("#"):
        lines = lines[1:]

    cleaned_tokens = []
    in_code_block = False
    for line in lines:
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        # Strip markdown headers, bold, italics, checklists
        line = line.lstrip("# \t-*+>")
        if line.startswith("[ ]") or line.startswith("[x]") or line.startswith("[X]"):
            line = line[3:].strip()
        line = line.replace("**", "").replace("*", "").replace("`", "")
        if line:
            cleaned_tokens.append(line)
        if len(" ".join(cleaned_tokens)) >= max_chars:
            break

    text = " ".join(cleaned_tokens).strip()
    text = " ".join(text.split())  # normalize whitespace
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text or "Empty note..."
