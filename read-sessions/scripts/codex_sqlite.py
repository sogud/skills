"""Read-only Codex session discovery and persisted UI-history projection.

Metadata queries never select titles, first messages or item_json. Stored item
bodies are read only when a caller explicitly opens a thread.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing

TOOL_FIELDS = {
    "commandExecution": (("command", "cwd", "commandActions"), ("status", "aggregatedOutput", "exitCode", "durationMs")),
    "fileChange": (("changes",), ("status",)),
    "mcpToolCall": (("server", "tool", "arguments"), ("status", "result", "error", "durationMs")),
    "dynamicToolCall": (("namespace", "tool", "arguments"), ("status", "contentItems", "success", "durationMs")),
    "collabAgentToolCall": (("tool", "receiverThreadIds", "prompt", "model", "reasoningEffort"), ("status", "agentsStates")),
    "webSearch": (("query", "action"), ("results",)),
    "imageView": (("path",), ()),
    "imageGeneration": (("revisedPrompt", "transparentBackground"), ("status", "result", "failure", "savedPath")),
    "sleep": (("durationMs",), ()),
}


def database_files(home):
    home = Path(home)
    def latest(prefix):
        for folder in (home, home / "sqlite"):
            matches = []
            for path in folder.glob(prefix + "_*.sqlite"):
                match = re.fullmatch(re.escape(prefix) + r"_(\d+)\.sqlite", path.name)
                if match:
                    matches.append((int(match[1]), path))
            if matches:
                return str(max(matches)[1])
        return None
    return latest("state"), latest("thread_history")


def connect(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def table_exists(connection, name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def is_subagent(value):
    if value == "subagent":
        return True
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and bool(parsed.get("subagent"))


def jsonl_header(path):
    with open(path, encoding="utf-8", errors="replace") as source:
        for line in source:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("type") == "session_meta":
                payload = record.get("payload") or {}
                return payload if isinstance(payload, dict) else {}
            if record.get("type") in ("response_item", "event_msg"):
                break
    return {}


def catalogue(home, cwd=None):
    """Merge registry/history IDs with JSONL headers, without reading dialogue."""
    home = Path(home)
    state, history = database_files(home)
    sessions = {}
    child_ids = set()
    try:
        if state:
            with closing(connect(state)) as db:
                if not table_exists(db, "threads"):
                    raise ValueError("Codex state database has no threads table")
                columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
                if "id" not in columns:
                    raise ValueError("Codex threads schema is missing id")
                names = ["id", "cwd", "rollout_path", "source", "thread_source", "updated_at_ms", "archived"]
                selection = ",".join(name if name in columns else "NULL AS " + name for name in names)
                for row in db.execute("SELECT " + selection + " FROM threads"):
                    data = dict(row)
                    thread_id = data.pop("id")
                    sessions[thread_id] = {"id": thread_id, **data, "registered": True,
                                           "has_history": False, "item_count": 0,
                                           "user_items": 0, "assistant_items": 0, "tool_items": 0,
                                           "jsonl_paths": []}
                if table_exists(db, "thread_spawn_edges"):
                    child_ids = {row[0] for row in db.execute("SELECT child_thread_id FROM thread_spawn_edges")}
        if history:
            with closing(connect(history)) as db:
                if not table_exists(db, "thread_items"):
                    raise ValueError("Codex history database has no thread_items table")
                kinds = ",".join("'" + kind + "'" for kind in TOOL_FIELDS)
                query = ("SELECT thread_id,count(*) AS item_count,max(created_at_ms) AS last_item_ms,"
                         "sum(item_type='userMessage') AS user_items,"
                         "sum(item_type='agentMessage') AS assistant_items,"
                         f"sum(item_type IN ({kinds})) AS tool_items FROM thread_items GROUP BY thread_id")
                for row in db.execute(query):
                    thread_id = row["thread_id"]
                    data = sessions.setdefault(thread_id, {"id": thread_id, "registered": False, "jsonl_paths": []})
                    data.update({key: row[key] for key in ["item_count", "user_items", "assistant_items", "tool_items"]})
                    data["has_history"] = True
                    if data.get("updated_at_ms") is None:
                        data["updated_at_ms"] = row["last_item_ms"]
    except sqlite3.Error as error:
        raise ValueError(f"Codex SQLite metadata read failed: {error}") from error

    paths = set()
    for folder in (home / "sessions", home / "archived_sessions"):
        if folder.exists():
            paths.update(folder.rglob("*.jsonl"))
    for data in sessions.values():
        path = data.get("rollout_path")
        if path and Path(path).suffix == ".jsonl" and Path(path).is_file():
            paths.add(Path(path))
    for path in sorted(paths):
        try:
            header = jsonl_header(path)
            stat = path.stat()
        except OSError:
            continue
        thread_id = header.get("id") or header.get("session_id")
        key = thread_id or str(path.resolve())
        data = sessions.setdefault(key, {"id": thread_id, "registered": False, "has_history": False,
                                         "item_count": 0, "user_items": 0, "assistant_items": 0,
                                         "tool_items": 0, "jsonl_paths": []})
        # A registry path may be stale or shared. Associate a file only with its own header ID.
        data["jsonl_paths"].append(str(path.resolve()))
        if not data.get("cwd"):
            data["cwd"] = header.get("cwd")
        if data.get("updated_at_ms") is None:
            data["updated_at_ms"] = int(stat.st_mtime * 1000)
        if is_subagent(header.get("source")):
            child_ids.add(key)
    result = []
    for key, data in sessions.items():
        data["kind"] = "subagent" if key in child_ids or is_subagent(data.get("source")) or is_subagent(data.get("thread_source")) else ("main" if data["registered"] else "unknown")
        data["archived"] = bool(data.get("archived"))
        data["jsonl_paths"] = sorted(set(data["jsonl_paths"]))
        raw_target = None
        if data["jsonl_paths"]:
            canonical = str(Path(data["rollout_path"]).resolve()) if data.get("rollout_path") else None
            raw_target = canonical if canonical in data["jsonl_paths"] else max(data["jsonl_paths"], key=os.path.getmtime)
        data["target"] = raw_target or (f"codex:{data['id']}" if data["has_history"] else None)
        if cwd and (not data.get("cwd") or os.path.abspath(data["cwd"]) != os.path.abspath(os.path.expanduser(cwd))):
            continue
        result.append(data)
    return sorted(result, key=lambda data: data.get("updated_at_ms") or 0, reverse=True)


def inventory(sessions):
    return {"agent": "codex", "sessions": len(sessions),
            "registered": sum(data["registered"] for data in sessions),
            "main": sum(data["kind"] == "main" for data in sessions),
            "subagent": sum(data["kind"] == "subagent" for data in sessions),
            "unknown": sum(data["kind"] == "unknown" for data in sessions),
            "with_sqlite_history": sum(data["has_history"] for data in sessions),
            "history_only": sum(data["has_history"] and not data["registered"] for data in sessions),
            "with_jsonl": sum(bool(data["jsonl_paths"]) for data in sessions),
            "dialogue_indexed": sum(bool(data.get("user_items") and data.get("assistant_items")) for data in sessions),
            "main_dialogue_indexed": sum(data["kind"] == "main" and bool(data.get("user_items") and data.get("assistant_items")) for data in sessions),
            "metadata_only": sum(data["target"] is None for data in sessions)}


def require_history(home, thread_id):
    _state, history = database_files(home)
    if not history:
        raise ValueError("Codex SQLite history database not found")
    try:
        with closing(connect(history)) as db:
            found = db.execute("SELECT 1 FROM thread_items WHERE thread_id=? LIMIT 1", (thread_id,)).fetchone()
    except sqlite3.Error as error:
        raise ValueError(f"Codex SQLite history read failed: {error}") from error
    if not found:
        raise ValueError(f"Codex thread {thread_id} has no stored history items; metadata is not a transcript")
    return history


def project_item(row, item, database, thread_id):
    """Project saved UI fields, not an invented original provider request."""
    kind = row["item_type"]
    location = {"backend": "codex_sqlite", "database": database, "thread_id": thread_id,
                "item_id": row["item_id"], "rollout_ordinal": row["rollout_ordinal"], "item_type": kind}
    record = {"timestamp": row["created_at_ms"], "source_ref": location}
    if kind == "userMessage":
        return {**record, "type": "user", "message": {"content": item.get("content", [])}}
    if kind == "agentMessage":
        return {**record, "type": "assistant", "message": {"content": item.get("text", "")}}
    call_id = "sqlite:" + row["item_id"]
    if kind == "functionCallOutput":
        return {**record, "type": "message", "message": {"role": "toolResult", "toolCallId": call_id,
                "toolName": item.get("name", kind), "content": item.get("output", "")}}
    if item.get("status") is not None:
        record["tool_status"] = item["status"]
    input_fields, output_fields = TOOL_FIELDS[kind]
    arguments = {key: item[key] for key in input_fields if key in item and item[key] is not None}
    output = {key: item[key] for key in output_fields if key in item and item[key] is not None}
    name = item.get("tool") or kind
    if kind == "mcpToolCall" and item.get("server"):
        name = f"{item['server']}/{name}"
    blocks = [{"type": "tool_use", "id": call_id, "name": name, "input": arguments}]
    if output:
        blocks.append({"type": "tool_result", "tool_use_id": call_id, "content": output})
    return {**record, "type": "assistant", "message": {"content": blocks}}


def projected_records(home, thread_id, database=None):
    """Selectors use rollout_ordinal + 1; raw bytes fingerprint the stored rows."""
    database = database or require_history(home, thread_id)
    supported = set(TOOL_FIELDS) | {"userMessage", "agentMessage", "functionCallOutput"}
    try:
        with closing(connect(database)) as db:
            query = ("SELECT item_id,item_type,rollout_ordinal,created_at_ms,updated_at_ordinal,item_json "
                     "FROM thread_items WHERE thread_id=? ORDER BY rollout_ordinal,item_id")
            previous = None
            for row in db.execute(query, (thread_id,)):
                ordinal = row["rollout_ordinal"]
                if not isinstance(ordinal, int) or ordinal < 0 or ordinal == previous:
                    raise ValueError("Codex history has invalid or duplicate rollout ordinals")
                previous = ordinal
                raw = (json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                record = None
                if row["item_type"] in supported:
                    try:
                        item = json.loads(row["item_json"])
                    except ValueError as error:
                        raise ValueError(f"Invalid Codex stored item at ordinal {ordinal}") from error
                    if not isinstance(item, dict):
                        raise ValueError(f"Codex stored item at ordinal {ordinal} is not an object")
                    record = project_item(row, item, database, thread_id)
                yield ordinal + 1, record, raw
    except sqlite3.Error as error:
        raise ValueError(f"Codex SQLite history read failed: {error}") from error
