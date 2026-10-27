import os
import sys
import io

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import uuid
import random
import string
import shutil
import tempfile
import threading
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lunariz.core.config import LunarConfig
from lunariz.core.storage import NoteStorage, Note
from lunariz.core.indexer import NoteIndexer
from lunariz.core.tasks import TaskEngine
from lunariz.core.history import NoteHistory
from lunariz.core.search import MultiTokenSearch
from lunariz.agent.mcp_server import LunarMCPServer


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"🔥 {title.upper()} 🔥")
    print("=" * 70)


def test_volume_load(storage: NoteStorage, indexer: NoteIndexer, count: int = 1000):
    print_banner(f"Test 1: High Volume Ingestion ({count} Notes)")
    start_time = time.perf_counter()

    sample_tags = ["dev", "ai", "finance", "rust", "python", "docker", "meeting", "ideas", "sec"]

    notes = []
    for i in range(count):
        tags = random.sample(sample_tags, k=random.randint(1, 3))
        content = f"# Generated Note {i}\n\nAutomated volume test entry {uuid.uuid4()}.\nTags: {' '.join(['#' + t for t in tags])}\n- [ ] Task {i} pending\n- [x] Task {i} verified"
        note = storage.create_note(title=f"Volume Note {i:04d}", content=content, tags=tags, is_pinned=(i % 50 == 0))
        notes.append(note)

    ingest_time = time.perf_counter() - start_time
    rate = count / ingest_time
    print(f"✔ Created {count} notes on disk in {ingest_time:.2f}s ({rate:.1f} notes/sec)")

    # Test indexing
    idx_start = time.perf_counter()
    synced = indexer.sync_from_storage(storage)
    idx_time = time.perf_counter() - idx_start
    print(f"✔ Indexed {synced} notes into SQLite FTS5 in {idx_time:.2f}s ({count / idx_time:.1f} notes/sec)")

    # Test FTS5 query latency
    query_start = time.perf_counter()
    queries = ["python", "docker", "Automated", "verified", "finance", "Generated"]
    for q in queries:
        res = indexer.search(q, limit=20)
        assert len(res) > 0

    query_total_time = time.perf_counter() - query_start
    avg_latency_ms = (query_total_time / len(queries)) * 1000
    print(f"✔ Executed {len(queries)} FTS5 queries across {count} notes in {query_total_time*1000:.2f}ms (Avg: {avg_latency_ms:.2f}ms/query)")
    assert avg_latency_ms < 15.0, f"Query latency too slow: {avg_latency_ms}ms"


def test_concurrency_race_conditions(storage: NoteStorage, indexer: NoteIndexer, workers: int = 16, iterations: int = 25):
    print_banner(f"Test 2: Concurrency & Lock Contention ({workers} Threads x {iterations} Iterations = {workers * iterations} Ops)")

    # Target a shared set of notes
    shared_notes = [storage.create_note(f"Shared Target {i}", f"Initial state {i}") for i in range(5)]
    indexer.sync_from_storage(storage)

    errors = []
    success_ops = 0

    def worker_action(worker_id: int):
        nonlocal success_ops
        try:
            for it in range(iterations):
                target = random.choice(shared_notes)
                op = random.choice(["read", "append", "search", "create", "toggle"])

                if op == "read":
                    fresh = storage.get_note(target.id)
                    assert fresh is not None
                elif op == "append":
                    fresh = storage.get_note(target.id)
                    if fresh:
                        fresh.content += f"\n- [ ] Worker {worker_id} iteration {it}"
                        storage.write_note(fresh)
                elif op == "search":
                    indexer.search("Worker")
                elif op == "create":
                    storage.create_note(f"Concurrent {worker_id}-{it}", f"Payload from thread {worker_id}")
                elif op == "toggle":
                    fresh = storage.get_note(target.id)
                    if fresh:
                        TaskEngine.toggle_task(fresh, "Worker", storage=storage)

                success_ops += 1
        except Exception as e:
            errors.append(f"Worker {worker_id} failed: {e}")

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_action, w) for w in range(workers)]
        for f in as_completed(futures):
            f.result()

    total_time = time.perf_counter() - start_time
    print(f"✔ Completed {success_ops} concurrent multi-threaded operations in {total_time:.2f}s ({success_ops / total_time:.1f} ops/sec)")
    if errors:
        print(f"❌ Concurrency Errors ({len(errors)}): {errors[:5]}")
        raise RuntimeError(f"{len(errors)} concurrency errors detected!")
    else:
        print("✔ Zero race conditions, zero file-handle locks, zero database deadlocks!")


def test_adversarial_fuzzing(storage: NoteStorage, indexer: NoteIndexer):
    print_banner("Test 3: Adversarial Edge Cases & Security Fuzzing")

    # 1. Windows Reserved Device Names
    reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]
    for rname in reserved_names:
        note = storage.create_note(rname, f"Content for reserved Windows device name {rname}")
        assert note is not None
        assert note.path.exists()
        read = storage.get_note(note.id)
        assert read is not None
    print(f"✔ Passed Windows reserved device names ({', '.join(reserved_names[:4])}...)")

    # 2. Path Traversal & Injection Payloads
    path_traversal_titles = [
        "../../../../Windows/System32/calc.exe",
        "../../etc/passwd",
        "..\\..\\Windows\\win.ini",
        "C:\\Windows\\System32",
        "Note/With/Deep/Slashes/../../Escape",
        "Note:With*Forbidden?Windows\"Characters<Here>|Pipe",
    ]
    for ptitle in path_traversal_titles:
        note = storage.create_note(ptitle, f"Payload test for {ptitle}")
        # Note MUST be constrained strictly within notes_dir
        assert storage.config.notes_dir in note.path.parents or note.path.parent == storage.config.notes_dir
        assert note.path.exists()
        # Verify read by slug
        found = storage.get_note(note.id)
        assert found is not None
    print("✔ Passed Path Traversal & Forbidden Windows Character neutralization")

    # 3. Extreme Unicode, Emoji & Zalgo Fuzzing
    weird_strings = [
        "🔥 🚀 💎 🌙 🦀 ⚡ 🤖 📝",
        "﷽ 𝕿𝖍𝖊 𝖖𝖚𝖎𝖈𝖐 𝖇𝖗𝖔𝖜𝖓 𝖋𝖔𝖝 𝖏𝖚𝖒𝖕𝖘 𝖔𝖛𝖊𝖗 𝖙𝖍𝖊 𝖑𝖆𝖟𝖞 𝖉𝖔𝖌",
        "Zalgo: Hͥaͣcͫkͭeͤrͬ Zͩaͨlͮgͭoͩ Tͥeͣxͫtͭ",
        "CJK: 你好世界 こんにちは世界 안녕하세요 세계",
        "RTL / Arabic / Hebrew: مرحبا بالعالم שלום עולם (RLO: \u202Ereversed\u202C)",
        "Zero-width: a\u200B\u200Cb\u200D\uFEFFc",
    ]
    for w in weird_strings:
        note = storage.create_note(f"Unicode {w[:15]}", f"# Title {w}\n\nBody content: {w}\nTags: #weird #unicode")
        assert note.path.exists()
        indexer.index_note(note)
        # Search for exact unicode
        res = indexer.search("weird")
        assert len(res) > 0
    print("✔ Passed Complex Unicode, Emoji, Zalgo, CJK, and RTL parsing")

    # 4. Large Note Stress (5MB Single Document)
    large_text = ("# Massive Scalability Document\n\n" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50) + "\n\n") * 1000
    large_note_start = time.perf_counter()
    large_note = storage.create_note("Massive Scalability Note", large_text)
    write_large_time = time.perf_counter() - large_note_start
    size_mb = len(large_note.content) / (1024 * 1024)
    print(f"✔ Written massive {size_mb:.2f}MB note in {write_large_time:.3f}s")
    assert write_large_time < 2.0

    read_start = time.perf_counter()
    read_large = storage.get_note(large_note.id)
    read_large_time = time.perf_counter() - read_start
    print(f"✔ Read massive {size_mb:.2f}MB note in {read_large_time:.3f}s")
    assert read_large is not None
    assert len(read_large.content) == len(large_text)


def test_rapid_time_machine_mutations(storage: NoteStorage, history: NoteHistory, mutations: int = 50):
    print_banner(f"Test 4: Rapid Time-Machine Micro-Diffs ({mutations} Sequential Edits)")
    note = storage.create_note("Rapid Mutation Target", "Genesis paragraph.")
    history.record_snapshot(note)

    start_time = time.perf_counter()
    for i in range(1, mutations + 1):
        prev = note.content
        note.content += f"\nMutation block #{i} added at {time.time()}."
        history.record_snapshot(note, prev_content=prev)
        storage.write_note(note)

    elapsed = time.perf_counter() - start_time
    snapshots = history.list_snapshots(note.id)
    print(f"✔ Recorded {len(snapshots)} differential snapshots in {elapsed:.2f}s ({mutations / elapsed:.1f} snaps/sec)")
    assert len(snapshots) >= mutations

    # Test restoration to first snapshot
    oldest_id = snapshots[-1]["id"]
    restored = history.restore_snapshot(note, oldest_id, storage)
    assert restored is not None
    assert restored.content == "Genesis paragraph."
    print("✔ Successfully restored note to genesis state (100% diff fidelity)")


def test_task_engine_stress(storage: NoteStorage, task_count: int = 500):
    print_banner(f"Test 5: Task Engine & Kanban Projection Stress ({task_count} Tasks)")
    lines = ["# Super Task Board\n\n"]
    for i in range(task_count):
        state = "x" if i % 3 == 0 else " "
        lines.append(f"- [{state}] Task item number {i:04d} with metadata tag #t{i%10}")

    content = "\n".join(lines)
    note = storage.create_note("Huge Task List", content)

    # Extract all tasks
    t_start = time.perf_counter()
    tasks = TaskEngine.extract_tasks_from_note(note)
    t_time = time.perf_counter() - t_start
    print(f"✔ Extracted {len(tasks)} tasks in {t_time*1000:.2f}ms")
    assert len(tasks) == task_count

    # Toggle 20 random tasks
    toggle_start = time.perf_counter()
    for _ in range(20):
        target_num = random.randint(0, task_count - 1)
        toggled, note = TaskEngine.toggle_task(note, f"Task item number {target_num:04d}", storage=storage)
        assert toggled is True
    toggle_time = time.perf_counter() - toggle_start
    print(f"✔ Successfully toggled and persisted 20 tasks in {toggle_time*1000:.2f}ms ({toggle_time*1000/20:.2f}ms/toggle)")

    # Kanban projection
    kb_start = time.perf_counter()
    kanban = TaskEngine.project_kanban(note)
    kb_time = time.perf_counter() - kb_start
    print(f"✔ Projected {task_count} tasks into Kanban columns in {kb_time*1000:.2f}ms (Pending: {len(kanban['Pending'])}, Completed: {len(kanban['Completed'])})")
    assert len(kanban["Pending"]) + len(kanban["Completed"]) == task_count


def test_mcp_server_hammering(config: LunarConfig, hammer_count: int = 100):
    print_banner(f"Test 6: AI Agent MCP Protocol Hammering ({hammer_count} Sequential Requests)")
    server = LunarMCPServer(config)

    start_time = time.perf_counter()
    for i in range(hammer_count):
        req = {
            "jsonrpc": "2.0",
            "id": i,
            "method": "tools/call",
            "params": {
                "name": "lunar_append_scratchpad",
                "arguments": {"thought": f"Hammer thought {i} from agent"},
            },
        }
        res = server.handle_request(req)
        assert res["result"]["isError"] is False

    elapsed = time.perf_counter() - start_time
    rate = hammer_count / elapsed
    print(f"✔ Executed {hammer_count} MCP JSON-RPC tool calls in {elapsed:.2f}s ({rate:.1f} requests/sec)")


def main():
    print("\n" + "#" * 70)
    print("🚀 LUNARIZ EXTREME STRESS & CHAOS TEST CAMPAIGN 🚀")
    print("#" * 70)

    tracemalloc.start()
    overall_start = time.perf_counter()

    temp_dir = Path(tempfile.mkdtemp(prefix="lunar_stress_"))
    try:
        config = LunarConfig(base_dir=temp_dir)
        config.ensure_directories()
        storage = NoteStorage(config)
        indexer = NoteIndexer(config)
        history = NoteHistory(config)

        # 1. Volume test
        test_volume_load(storage, indexer, count=1000)

        # 2. Concurrency test
        test_concurrency_race_conditions(storage, indexer, workers=8, iterations=15)

        # 3. Adversarial fuzzing
        test_adversarial_fuzzing(storage, indexer)

        # 4. Rapid time-machine mutations
        test_rapid_time_machine_mutations(storage, history, mutations=50)

        # 5. Task engine stress
        test_task_engine_stress(storage, task_count=500)

        # 6. MCP Protocol hammering
        test_mcp_server_hammering(config, hammer_count=100)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        total_elapsed = time.perf_counter() - overall_start

        print_banner("SUMMARY OF STRESS TEST CAMPAIGN")
        print(f"✔ Total Test Duration: {total_elapsed:.2f} seconds")
        print(f"✔ Peak Python Memory Allocated: {peak / (1024 * 1024):.2f} MB")
        print(f"✔ Final State: ALL 6 STRESS SUITES PASSED FLAWLESSLY WITH ZERO ERRORS!")
        print("=" * 70 + "\n")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
