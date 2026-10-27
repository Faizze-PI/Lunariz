import json
import pytest
from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage
from lunariz.core.indexer import NoteIndexer
from lunariz.agent.mcp_server import LunarMCPServer


@pytest.fixture
def temp_config(tmp_path):
    config = LunarConfig(base_dir=tmp_path)
    config.ensure_directories()
    return config


def test_mcp_server_initialize_and_tools_list(temp_config):
    server = LunarMCPServer(temp_config)

    # Initialize request
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_res = server.handle_request(init_req)
    assert init_res["result"]["serverInfo"]["name"] == "lunariz-notes"

    # Tools list request
    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tools_res = server.handle_request(tools_req)
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    assert "lunar_create_note" in tool_names
    assert "lunar_search_notes" in tool_names
    assert "lunar_get_tasks" in tool_names


def test_mcp_server_crud_and_task_execution(temp_config):
    server = LunarMCPServer(temp_config)

    # 1. Create Note tool
    create_call = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "lunar_create_note",
            "arguments": {
                "title": "Agent Research Report",
                "content": "# Agent Research\n- [ ] Analyze dataset\n- [x] Run baseline tests",
                "tags": ["agent", "research"],
            },
        },
    }
    create_res = server.handle_request(create_call)
    assert create_res["result"]["isError"] is False
    created_note = json.loads(create_res["result"]["content"][0]["text"])
    assert created_note["title"] == "Agent Research Report"

    # 2. Search Note tool
    search_call = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "lunar_search_notes",
            "arguments": {"query": "dataset"},
        },
    }
    search_res = server.handle_request(search_call)
    results = json.loads(search_res["result"]["content"][0]["text"])
    assert len(results) == 1
    assert results[0]["title"] == "Agent Research Report"

    # 3. Get Tasks tool
    tasks_call = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "lunar_get_tasks",
            "arguments": {"status": "pending"},
        },
    }
    tasks_res = server.handle_request(tasks_call)
    tasks = json.loads(tasks_res["result"]["content"][0]["text"])
    assert len(tasks) == 1
    assert tasks[0]["text"] == "Analyze dataset"

    # 4. Toggle Task tool
    toggle_call = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": "lunar_toggle_task",
            "arguments": {"task_text": "Analyze dataset", "is_completed": True},
        },
    }
    toggle_res = server.handle_request(toggle_call)
    assert toggle_res["result"]["isError"] is False

    # 5. Scratchpad tool
    scratch_call = {
        "jsonrpc": "2.0",
        "id": 14,
        "method": "tools/call",
        "params": {
            "name": "lunar_append_scratchpad",
            "arguments": {"thought": "Finished analyzing baseline accuracy."},
        },
    }
    scratch_res = server.handle_request(scratch_call)
    assert scratch_res["result"]["isError"] is False
    scratch_data = json.loads(scratch_res["result"]["content"][0]["text"])
    assert "Finished analyzing baseline accuracy" in scratch_data["content"]
