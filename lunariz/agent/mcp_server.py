import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable

from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage
from lunariz.core.indexer import NoteIndexer
from lunariz.core.tasks import TaskEngine
from lunariz.agent.schemas import MCP_TOOLS

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lunar_mcp")


class LunarMCPServer:
    """Model Context Protocol (MCP) server for AI agents with modular tool dispatch."""

    def __init__(self, config: Optional[LunarConfig] = None):
        self.config = config or LunarConfig().load_from_file()
        self.storage = NoteStorage(self.config)
        self.indexer = NoteIndexer(self.config)

        # Dispatch table mapping tool names to isolated handlers
        self._tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "lunar_search_notes": self._tool_search_notes,
            "lunar_read_note": self._tool_read_note,
            "lunar_create_note": self._tool_create_note,
            "lunar_append_note": self._tool_append_note,
            "lunar_get_tasks": self._tool_get_tasks,
            "lunar_toggle_task": self._tool_toggle_task,
            "lunar_append_scratchpad": self._tool_append_scratchpad,
        }

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatch JSON-RPC 2.0 requests."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "lunariz-notes", "version": "1.0.0"},
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                result = self.execute_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}],
                        "isError": False,
                    },
                }
            except Exception as e:
                logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Route tool call via dispatch dictionary with O(1) lookup."""
        handler = self._tool_handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        return handler(args)

    # -------------------------------------------------------------
    # Tool Handler Subroutines (Single-Responsibility)
    # -------------------------------------------------------------
    def _tool_search_notes(self, args: Dict[str, Any]) -> Any:
        query = args.get("query", "")
        tag = args.get("tag")
        limit = args.get("limit", 20)
        self.indexer.sync_from_storage(self.storage)
        return self.indexer.search(query, tag=tag, limit=limit)

    def _tool_read_note(self, args: Dict[str, Any]) -> Any:
        id_or_title = args.get("id_or_title", "")
        note = self.storage.get_note(id_or_title)
        if not note:
            raise ValueError(f"Note '{id_or_title}' not found.")
        return note.to_dict()

    def _tool_create_note(self, args: Dict[str, Any]) -> Any:
        title = args.get("title", "")
        content = args.get("content", "")
        tags = args.get("tags", [])
        is_pinned = args.get("is_pinned", False)
        note = self.storage.create_note(title=title, content=content, tags=tags, is_pinned=is_pinned)
        self.indexer.index_note(note)
        return note.to_dict()

    def _tool_append_note(self, args: Dict[str, Any]) -> Any:
        id_or_title = args.get("id_or_title", "")
        content_to_append = args.get("content", "")
        note = self.storage.get_note(id_or_title)
        if not note:
            raise ValueError(f"Note '{id_or_title}' not found.")
        note.content = f"{note.content.rstrip()}\n\n{content_to_append}\n"
        self.storage.write_note(note)
        self.indexer.index_note(note)
        return note.to_dict()

    def _tool_get_tasks(self, args: Dict[str, Any]) -> Any:
        status = args.get("status", "all")
        all_notes = self.storage.list_notes()
        tasks = []
        for note in all_notes:
            for t in TaskEngine.extract_tasks_from_note(note):
                if status == "pending" and t.is_done:
                    continue
                if status == "completed" and not t.is_done:
                    continue
                tasks.append(t.to_dict())
        return tasks

    def _tool_toggle_task(self, args: Dict[str, Any]) -> Any:
        task_text = args.get("task_text", "")
        is_completed = args.get("is_completed")
        for note in self.storage.list_notes():
            toggled, _ = TaskEngine.toggle_task(note, task_text, target_state=is_completed, storage=self.storage)
            if toggled:
                self.indexer.index_note(note)
                return {"toggled": True, "note_title": note.title, "task_text": task_text}
        raise ValueError(f"No task matching '{task_text}' was found.")

    def _tool_append_scratchpad(self, args: Dict[str, Any]) -> Any:
        thought = args.get("thought", "")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        scratch_title = f"{today_str} Scratchpad"
        scratch_note = self.storage.get_note(scratch_title)
        now_time = datetime.now().strftime("%I:%M %p")
        entry = f"### {now_time}\n{thought}\n"

        if scratch_note:
            scratch_note.content = f"{scratch_note.content.rstrip()}\n\n{entry}"
            self.storage.write_note(scratch_note)
        else:
            scratch_note = self.storage.create_note(
                title=scratch_title,
                content=f"# {scratch_title}\n\n{entry}",
                tags=["scratchpad", "daily"],
                is_pinned=True,
            )
        self.indexer.index_note(scratch_note)
        return scratch_note.to_dict()


def run_mcp_server() -> int:
    """Run JSON-RPC 2.0 loop reading from stdin and writing to stdout."""
    server = LunarMCPServer()
    logger.info("Lunariz MCP Server started.")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = server.handle_request(req)
            if res is not None:
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            logger.error(f"JSON-RPC parse error: {e}", exc_info=True)

    return 0


if __name__ == "__main__":
    sys.exit(run_mcp_server())
