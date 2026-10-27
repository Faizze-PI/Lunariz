"""Tool schemas for Model Context Protocol (MCP) server."""

MCP_TOOLS = [
    {
        "name": "lunar_search_notes",
        "description": "Search notes using full-text search and keyword tokens. Returns matching note summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query keywords"},
                "tag": {"type": "string", "description": "Optional tag to filter by"},
                "limit": {"type": "integer", "description": "Maximum notes to return", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lunar_read_note",
        "description": "Read the full markdown content and metadata of a note by title, ID, or slug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id_or_title": {"type": "string", "description": "Note title, ID, or slug"},
            },
            "required": ["id_or_title"],
        },
    },
    {
        "name": "lunar_create_note",
        "description": "Create a new note with title, markdown body, and tags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the note"},
                "content": {"type": "string", "description": "Markdown body content of the note"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags associated with the note",
                },
                "is_pinned": {"type": "boolean", "description": "Whether to pin the note to the top", "default": False},
            },
            "required": ["title"],
        },
    },
    {
        "name": "lunar_append_note",
        "description": "Append content to an existing note without overwriting prior content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id_or_title": {"type": "string", "description": "Target note title or ID"},
                "content": {"type": "string", "description": "Content to append"},
            },
            "required": ["id_or_title", "content"],
        },
    },
    {
        "name": "lunar_get_tasks",
        "description": "Retrieve GFM checklist items (- [ ] / - [x]) across all notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "completed", "all"],
                    "description": "Filter tasks by completion status",
                    "default": "all",
                },
            },
        },
    },
    {
        "name": "lunar_toggle_task",
        "description": "Toggle the completion state of a task checklist item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_text": {"type": "string", "description": "Substring of the task text to toggle"},
                "is_completed": {"type": "boolean", "description": "Target completion state (true=done, false=pending)"},
            },
            "required": ["task_text"],
        },
    },
    {
        "name": "lunar_append_scratchpad",
        "description": "Append a thought or log entry directly to today's daily scratchpad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Thought, snippet, or reminder to append"},
            },
            "required": ["thought"],
        },
    },
]
