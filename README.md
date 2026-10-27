# 🌙 Lunariz

> **Ultra-lightweight, calm desktop and CLI note-taking engine for humans and autonomous AI agents.**

Lunariz is engineered to give you the visual focus of a **native desktop application**, the scriptable speed of a **terminal CLI**, and the interoperability of an **AI Agent MCP Server**—all sharing the exact same transparent Markdown files on disk (`~/.lunar/notes/`).

---

## ⚡ Instant Download (No Python or Setup Required)

If you just want the desktop application without installing Python or dependencies:
1. Go to **[GitHub Releases](https://github.com/Faizze-PI/Lunariz/releases/latest)**.
2. Download **`Lunariz-Windows-x64.zip`**.
3. Extract and double-click **`Lunariz.exe`**.

That's it! It runs portably on any Windows 10/11 x64 PC with **zero external prerequisites**.

---

## ✨ Features

- 🖥️ **Native Windows Desktop Window**: Built with `CustomTkinter`. Modern card layout, DPI auto-scaling, Dark Zen & Warm Paper calm themes.
- 🎨 **Multi-View Canvas**: Seamlessly switch between **`✍️ Edit`**, **`👁️ Preview`** (Rich Markdown typography), and **`▦ Kanban`** (Interactive 3-column task board).
- ⌨️ **Keyboard-Driven Flow**: Floating Spotlight Command Palette (`Ctrl+K` / `Ctrl+P`) for instant navigation and action execution.
- ⚡ **High-Speed CLI Companion**: Cold-starts in **< 30ms**, instant multi-token search, stdin piping (`git log | lunar add ... --stdin`).
- 🤖 **First-Class AI Agent Interoperability**:
  - Deterministic `--json` output across all commands.
  - Embedded **Model Context Protocol (MCP)** server (`lunar mcp`) for Claude Desktop, Cursor, and Antigravity.
- 📝 **100% Data Sovereignty**: All notes are standard `.md` files in `~/.lunar/notes/`. Zero lock-in, zero cloud servers, zero telemetry.
- 🔍 **Sub-2ms Full-Text Search**: In-memory token scoring backed by SQLite FTS5 in `WAL` mode.
- ⏪ **Offline Time-Machine**: Reversible micro-diff history snapshots and 1-click restore.
- 📋 **Checklist & Kanban Projection**: GFM task items (`- [ ]`, `- [x]`) toggleable in both GUI and CLI.

---

## 🚀 Developer & CLI Installation

### 1. Install via pip
If you are a developer or want the CLI commands globally:
```powershell
git clone https://github.com/Faizze-PI/Lunariz.git
cd Lunariz
pip install -e .
```

### 2. Launch the Desktop GUI
```powershell
lunar app
```

### 3. CLI Usage

```powershell
# Create a note
lunar add "Sprint Architecture" --content "# Sprint\n- [ ] Deploy v1" --tags "dev,systems"

# Search notes
lunar search "architecture"

# List notes
lunar list --pinned

# Quick scratchpad (appends to today's daily log)
lunar scratch "Follow up with server team on Friday"

# View all pending tasks
lunar tasks --pending

# Check off a task directly from terminal
lunar tasks --toggle "Deploy v1"

# Output pure JSON for scripts or AI agents
lunar search "architecture" --json
```

### 4. Connect to Claude Desktop / Cursor / Antigravity via MCP
Add the following snippet to your `claude_desktop_config.json` or `mcpServers` configuration:

```json
{
  "mcpServers": {
    "lunariz": {
      "command": "lunar",
      "args": ["mcp"]
    }
  }
}
```

---

## ⌨️ Desktop Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl + K` / `Ctrl + P` | Open Floating Spotlight Command Palette |
| `Ctrl + N` | Create New Note |
| `Ctrl + F` | Jump & focus Note Search Bar |
| `Ctrl + S` | Force Immediate Disk Save |
| `Ctrl + E` | Switch to Live Edit Mode |
| `Ctrl + Shift + P` | Switch to Markdown Typography Preview |
| `Ctrl + Shift + K` | Switch to Embedded Kanban Board |

---

## 📂 Storage Architecture

```
~/.lunar/
├── config.json          # User settings (theme, defaults)
├── index.db             # High-speed SQLite FTS5 query cache
├── .trash/              # Soft-deleted notes for recovery
├── .history/            # Micro-diff revision snapshots
└── notes/               # Human-readable Markdown files
    ├── 2026-10-26-sprint-architecture.md
    └── 2026-10-26-scratchpad.md
```

---

## 📜 License

MIT License. Free and open source.
