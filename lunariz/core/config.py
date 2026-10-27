import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any

DEFAULT_THEME_WARM = {
    "name": "Warm Paper",
    "bg_main": "#FBF9F5",
    "bg_card": "#FFFFFF",
    "bg_sidebar": "#F4EFE6",
    "text_primary": "#282725",
    "text_muted": "#7D7A75",
    "accent": "#D97706",
    "border": "#E6DFD5",
    "card_shadow": "#D6CEC2",
}

DEFAULT_THEME_DARK = {
    "name": "Dark Zen",
    "bg_main": "#161614",
    "bg_card": "#1E1E1B",
    "bg_sidebar": "#121210",
    "text_primary": "#E6E4DE",
    "text_muted": "#8A8780",
    "accent": "#818CF8",
    "border": "#2A2A26",
    "card_shadow": "#0A0A08",
}


@dataclass
class LunarConfig:
    base_dir: Path = field(default_factory=lambda: Path(os.environ.get("LUNAR_HOME", Path.home() / ".lunar")))
    theme: str = "dark"  # "dark" or "warm"
    auto_save_delay_ms: int = 300
    default_tags: list = field(default_factory=list)

    @property
    def notes_dir(self) -> Path:
        return self.base_dir / "notes"

    @property
    def trash_dir(self) -> Path:
        return self.base_dir / ".trash"

    @property
    def history_dir(self) -> Path:
        return self.base_dir / ".history"

    @property
    def db_path(self) -> Path:
        return self.base_dir / "index.db"

    @property
    def config_file(self) -> Path:
        return self.base_dir / "config.json"

    def ensure_directories(self) -> None:
        """Create required directories safely."""
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def load_from_file(self) -> "LunarConfig":
        """Load user settings from config.json if present."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "theme" in data:
                        self.theme = data["theme"]
                    if "auto_save_delay_ms" in data:
                        self.auto_save_delay_ms = data["auto_save_delay_ms"]
                    if "default_tags" in data:
                        self.default_tags = data["default_tags"]
            except Exception:
                pass
        return self

    def save_to_file(self) -> None:
        """Persist current settings to config.json."""
        self.ensure_directories()
        data = {
            "theme": self.theme,
            "auto_save_delay_ms": self.auto_save_delay_ms,
            "default_tags": self.default_tags,
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_theme_tokens(self) -> Dict[str, Any]:
        """Return color tokens for current theme."""
        return DEFAULT_THEME_DARK if self.theme == "dark" else DEFAULT_THEME_WARM
