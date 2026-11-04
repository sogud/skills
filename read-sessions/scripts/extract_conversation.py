#!/usr/bin/env python3
"""Progressively read local Codex, Claude, Qoder and Pi session logs.

list -> tail (100 dialogue previews) -> show (one message) -> tools
export writes an AI analysis JSONL view or dialogue-only Markdown to Downloads.
Tool bodies are only printed for an explicit --call selector.
No clipboard access or automatic secret redaction. Original logs stay read-only.
"""
import argparse
import hashlib
import json
import os
import re
import sys

import codex_sqlite

CODEX_HOME = os.path.abspath(os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex")))

AGENT_DIRS = {
    "codex": os.path.join(CODEX_HOME, "sessions"),
    "claude": os.path.expanduser("~/.claude/projects"),
    "qoder": os.path.expanduser("~/.qoder/projects"),
    "pi": os.path.expanduser("~/.pi/agent/sessions"),
}

SKIP_PREFIXES = (
    "<local-command-caveat>",
    "<command-message>",
    "<system-reminder>",
    "Caveat: The messages below were generated",
    "# AGENTS.md instructions for ",
    "<environment_context>",
    "<skill>",
    "<recommended_plugins>",
    "<task-notification>",
    "<local-command-stdout>",
    "<local-command-stderr>",
)

LEADING_WRAPPER = re.compile(
    r"^<(system-reminder|environment_context|skill|recommended_plugins|task-notification|"
    r"local-command-caveat|command-message|local-command-stdout|local-command-stderr)"
    r"(?:\s[^>]*)?>.*?</\1>\s*", re.DOTALL,
)


def encode_cwd(cwd):
    return cwd.replace("/", "-")


def session_cwd(path):
    """Read the recorded workspace from the session header, not its filename."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "session_meta":
                return (record.get("payload") or {}).get("cwd")
            if record.get("type") == "session":
                return record.get("cwd")
            if record.get("type") in ("event_msg", "response_item", "message"):
                break
    return None


def iter_files(agent, cwd, limit=0):
    base = AGENT_DIRS[agent]
    if cwd:
        cwd = os.path.abspath(os.path.expanduser(cwd))
    if agent in ("claude", "qoder") and cwd:
        base = os.path.join(base, encode_cwd(cwd))
    hits = []
    for root, _dirs, names in os.walk(base):
        for name in names:
            if name.endswith(".jsonl"):
                path = os.path.join(root, name)
                try:
                    hits.append((os.path.getmtime(path), path))
                except OSError:
                    continue
    hits.sort(reverse=True)
    paths = []
    for _mtime, path in hits:
        if agent in ("codex", "pi") and cwd:
            recorded_cwd = session_cwd(path)
            if not recorded_cwd or os.path.abspath(recorded_cwd) != cwd:
                continue
        paths.append(path)
        if limit and len(paths) >= limit:
            break
    return paths


TEXT_BLOCK_TYPES = ("text", "input_text", "output_text")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in TEXT_BLOCK_TYPES:
                parts.append(block.get("text") or "")
        return "\n".join(p for p in parts if p)
    return ""


def codex_home():
    return os.path.dirname(os.path.abspath(AGENT_DIRS["codex"]))


def is_sqlite_session(target):
    return str(target).startswith("codex:")


def iter_records(path):
    """JSONL uses physical lines; SQLite uses rollout_ordinal + 1 selectors."""
    if is_sqlite_session(path):
        for ordinal, record, _raw in codex_sqlite.projected_records(codex_home(), path.removeprefix("codex:")):
            if record is not None:
                yield ordinal, record
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            try:
                record = json.loads(line)
            except ValueError:
                continue  # An active session may end with a partial record.
            if isinstance(record, dict):
                yield line_no, record


def dialogue_text(content):
    """Remove generated wrappers per text block without losing the user's request."""
    blocks = content if isinstance(content, list) else [content]
    parts = []
    for block in blocks:
        text = text_of([block] if isinstance(block, dict) else block).strip()
        while match := LEADING_WRAPPER.match(text):
            text = text[match.end():].lstrip()
        if text and not text.startswith(SKIP_PREFIXES):
            parts.append(text)
    return "\n".join(parts)


def dialogue(record):
    if record.get("isSidechain") or record.get("isMeta"):
        return None
    kind = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    if kind == "event_msg":
        role = {"user_message": "user", "agent_message": "assistant"}.get(payload.get("type"))
        text = dialogue_text(payload.get("message"))
    elif kind == "response_item":
        if payload.get("type") != "message" or payload.get("channel") == "analysis":
            return None
        role, text = payload.get("role"), dialogue_text(payload.get("content"))
    else:
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        if message.get("channel") == "analysis":
            return None
        role = message.get("role") if kind == "message" else kind
        text = dialogue_text(message.get("content"))
    text = text.strip()
    if role not in ("user", "assistant") or not text:
        return None
    if text == "[Request interrupted by user]":
        return None
    # Older Claude logs store compaction analysis/summary as an assistant text block.
    if role == "assistant" and text.startswith("<analysis>") and "<summary>" in text and text.endswith("</summary>"):
        return None
    return role, text


def record_timestamp(record):
    """Keep the logged value and unit; missing timestamps remain unknown."""
    for source in (record, record.get("message"), record.get("payload")):
        if isinstance(source, dict) and source.get("timestamp") is not None:
            return source["timestamp"]
    return None


def message_events(records):
    turn, previous = None, None
    for line, record in records:
        value = dialogue(record)
        if value is None:
            continue
        role, text = value
        source = record.get("type")
        # Codex can record the same message in both event_msg and response_item.
        # Only collapse adjacent cross-format copies, never repeated human text.
        if previous and previous[:2] == value and {previous[2], source} == {"event_msg", "response_item"}:
            continue
        if role == "user":
            turn = f"t{line}"
        message = {"id": f"m{line}", "line": line, "turn": turn, "role": role,
                   "text": text, "timestamp": record_timestamp(record)}
        if isinstance(record.get("source_ref"), dict):
            message["source_ref"] = record["source_ref"]
        yield message
        previous = (role, text, source)


def read_messages(path):
    return list(message_events(iter_records(path)))


def extract_messages(path):
    return [(m["role"], m["text"]) for m in read_messages(path)]


def compress(text, max_chars):
    """A bounded preview; use show for contiguous, unabridged text pages."""
    if len(text) <= max_chars:
        return text
    if max_chars < 3:
        return text[:max_chars]
    head = (max_chars - 1) * 2 // 3
    tail = max_chars - head - 1
    return text[:head] + "…" + text[-tail:]


def fmt_message(message, max_chars):
    return (f"[{message['id']} {message['turn'] or '-'} {message['role']} "
            f"chars={len(message['text'])}] " + compress(message["text"], max_chars))


def find_message(messages, message_id):
    for message in messages:
        if message["id"] == message_id:
            return message
    raise ValueError(f"message {message_id} not found; use an ID from tail")


def cmd_tail(path, n, before, max_chars, max_total_chars):
    messages = read_messages(path)
    if before:
        boundary = find_message(messages, before)["line"]
        eligible = [m for m in messages if m["line"] < boundary]
    else:
        eligible = messages
    selected, rendered = [], []
    header = f"session: {path} | conversation messages: {len(messages)}"
    used = len(header) + 200  # Reserve room for pagination metadata.
    for message in reversed(eligible[-n:]):
        text = fmt_message(message, max_chars)
        if used + len(text) + 2 > max_total_chars:
            if not selected:
                raise ValueError("page budget too small; lower --max-chars or raise --max-total-chars")
            break
        selected.insert(0, message)
        rendered.insert(0, text)
        used += len(text) + 2
    older = selected and any(m["line"] < selected[0]["line"] for m in eligible)
    cursor = selected[0]["id"] if older else "none"
    print(header)
    print(f"shown: {len(selected)} | older: {('--before ' + cursor) if older else 'none'}")
    print("\n\n".join(rendered))


def print_slice(text, offset, max_chars):
    if offset > len(text):
        raise ValueError(f"offset {offset} exceeds text length {len(text)}")
    end = min(offset + max_chars, len(text))
    print(f"chars: {offset}:{end}/{len(text)} | next: " + (f"--offset {end}" if end < len(text) else "none"))
    print(text[offset:end])


def cmd_show(path, message_id, offset, max_chars):
    message = find_message(read_messages(path), message_id)
    print(f"session: {path} | {message['id']} {message['turn'] or '-'} {message['role']}")
    print_slice(message["text"], offset, max_chars)


def cmd_list(agent, cwd, limit, metadata_only=False, count=False):
    if agent == "codex":
        sessions = codex_sqlite.catalogue(codex_home(), cwd)
        if count:
            print(json.dumps(codex_sqlite.inventory(sessions), ensure_ascii=False))
            return
        print(f"agent=codex home={codex_home()} sessions={len(sessions)} | metadata only")
        for i, session in enumerate(sessions[:limit], 1):
            target = session["target"] or f"codex:{session['id']} (metadata only; no stored transcript)"
            print(f"{i}. kind={session['kind']} | sqlite_items={session.get('item_count', 0)} | "
                  f"jsonl={len(session['jsonl_paths'])} | cwd={session.get('cwd') or 'unknown'}\n   {target}")
        return
    files = iter_files(agent, cwd, 0 if count else limit)
    if count:
        print(json.dumps({"agent": agent, "session_files": len(files)}, ensure_ascii=False))
        return
    print(f"agent={agent} dir={AGENT_DIRS[agent]} count={len(files)}")
    for i, path in enumerate(files, 1):
        if metadata_only:
            print(f"{i}. bytes={os.path.getsize(path)}\n   {path}")
            continue
        msgs = extract_messages(path)
        first_user = next((t for r, t in msgs if r == "user"), "").replace("\n", " ")[:80]
        import datetime
        day = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        print(f"{i}. {day} | {len(msgs)} 条 | {first_user}\n   {path}")


def protect_export_source(path, out):
    sources = [path]
    if is_sqlite_session(path):
        sources = [file + suffix for file in codex_sqlite.database_files(codex_home()) if file
                   for suffix in ("", "-wal", "-shm")]
    if os.path.exists(out) and any(os.path.exists(source) and os.path.samefile(source, out) for source in sources):
        raise ValueError("--out must not overwrite the source session log or database")


def cmd_extract(path, out, max_chars):
    protect_export_source(path, out)
    messages = read_messages(path)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# {os.path.basename(path)} conversation previews\n\n")
        f.write("\n\n".join(fmt_message(m, max_chars) for m in messages) + "\n")
    print(f"wrote {out} | {len(messages)} messages; previews only")


def open_export_output(path, export_format, out, output_dir):
    """Create a private export without replacing logs or existing user files."""
    if out:
        target = os.path.abspath(os.path.expanduser(out))
        protect_export_source(path, target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        return os.fdopen(descriptor, "w", encoding="utf-8"), target

    directory = os.path.abspath(os.path.expanduser(output_dir or "~/Downloads"))
    os.makedirs(directory, exist_ok=True)
    stem = ("codex-" + re.sub(r"[^a-zA-Z0-9._-]", "_", path.removeprefix("codex:"))
            if is_sqlite_session(path) else os.path.splitext(os.path.basename(path))[0])
    label, extension = ("analysis", "jsonl") if export_format == "jsonl" else ("simple", "md")
    number = 1
    while True:
        suffix = "" if number == 1 else f"-{number}"
        target = os.path.join(directory, f"{stem}.{label}{suffix}.{extension}")
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            number += 1
            continue
        return os.fdopen(descriptor, "w", encoding="utf-8"), target


def analysis_records(path, summary):
    """Read one UTF-8 source prefix, retaining only provenance and parse counts."""
    digest = hashlib.sha256()
    if is_sqlite_session(path):
        thread_id = path.removeprefix("codex:")
        summary.update(source_kind="codex_sqlite", fingerprint_scope="stored_thread_items",
                       source_database=codex_sqlite.require_history(codex_home(), thread_id))
        for ordinal, record, raw in codex_sqlite.projected_records(codex_home(), thread_id, summary["source_database"]):
            digest.update(raw)
            summary["source_bytes"] += len(raw)
            summary["source_records"] += 1
            if record is not None:
                yield ordinal, record
        summary["source_sha256"] = digest.hexdigest()
        return
    summary.update(source_kind="jsonl", fingerprint_scope="source_prefix")
    with open(path, "rb") as source:
        for line_no, raw in enumerate(source, 1):
            digest.update(raw)
            summary["source_bytes"] += len(raw)
            text = raw.decode("utf-8")
            if not text.strip():
                continue
            summary["source_records"] += 1
            try:
                record = json.loads(text)
            except ValueError:
                summary["invalid_json_lines"] += 1
                continue
            if not isinstance(record, dict):
                summary["non_object_lines"] += 1
                continue
            yield line_no, record
    summary["source_sha256"] = digest.hexdigest()


def build_analysis(path):
    summary = {"type": "session", "schema_version": 1, "source": path,
               "source_bytes": 0, "source_records": 0,
               "invalid_json_lines": 0, "non_object_lines": 0}
    calls, results = [], {}

    def records():
        for line, record in analysis_records(path, summary):
            for block, kind, call_id, name, value in tool_events(record):
                size = len(payload_text(value))
                if kind == "call":
                    indexed = {"type": "tool_call", "id": f"c{line}.{block}",
                               "line": line, "block": block, "call_id": call_id,
                               "name": name, "timestamp": record_timestamp(record),
                               "input_chars": size}
                    if isinstance(record.get("source_ref"), dict):
                        indexed["source_ref"] = record["source_ref"]
                    if record.get("tool_status") is not None:
                        indexed["status"] = record["tool_status"]
                    calls.append(indexed)
                else:
                    ref = {"line": line, "block": block, "chars": size,
                           "timestamp": record_timestamp(record)}
                    if isinstance(record.get("source_ref"), dict):
                        ref["source_ref"] = record["source_ref"]
                    results.setdefault(call_id, []).append(ref)
            yield line, record

    events = [{"type": "message", **message} for message in message_events(records())]
    matched_ids = set()
    for call in calls:
        refs = results.get(call["call_id"], []) if call["call_id"] else []
        if refs:
            matched_ids.add(call["call_id"])
        call.update(has_result=bool(refs), output_chars=sum(ref["chars"] for ref in refs), result_refs=refs)
        events.append(call)
    orphan_count = 0
    for call_id, refs in results.items():
        if call_id in matched_ids:
            continue
        for ref in refs:
            orphan = {"type": "tool_result", "call_id": call_id, "orphan": True,
                      "line": ref["line"], "block": ref["block"],
                      "timestamp": ref["timestamp"], "output_chars": ref["chars"]}
            if "source_ref" in ref:
                orphan["source_ref"] = ref["source_ref"]
            events.append(orphan)
            orphan_count += 1
    events.sort(key=lambda event: (event["line"], event.get("block", -1)))
    message_id = None
    for event in events:
        if event["type"] == "message" and event["role"] == "user":
            message_id = event["id"]
        elif event["type"] != "message":
            event["message_id"] = message_id
    summary.update(message_count=sum(event["type"] == "message" for event in events),
                   tool_call_count=len(calls), orphan_result_count=orphan_count)
    return summary, events


def cmd_export(path, export_format, out, output_dir):
    summary, events = build_analysis(path)
    messages = [event for event in events if event["type"] == "message"]
    if export_format == "md" and not messages:
        raise ValueError("no conversation messages found; use --format jsonl for a tool index")
    if not events:
        raise ValueError("no conversation messages or supported tool events found")
    stream, target = open_export_output(path, export_format, out, output_dir)
    with stream:
        if export_format == "jsonl":
            for event in [summary, *events]:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        else:
            stream.write(f"# 会话记录（简版）\n\n来源：{path}\n\n")
            for message in messages:
                role = "用户" if message["role"] == "user" else "助手"
                stream.write(f"## {role} · {message['id']}\n\n{message['text']}\n\n")
    print(f"wrote {target} | format={export_format} | {len(messages)} messages | "
          f"{summary['tool_call_count']} tool calls; dialogue unabridged")


def resolve_session(target):
    target = os.path.expanduser(target)
    if os.path.isfile(target):
        return os.path.abspath(target)
    if is_sqlite_session(target):
        thread_id = target.removeprefix("codex:")
        codex_sqlite.require_history(codex_home(), thread_id)
        return target
    candidates = []
    for session in codex_sqlite.catalogue(codex_home()):
        if (session["id"] and target.lower() in session["id"].lower()) or any(target.lower() in os.path.basename(path).lower() for path in session["jsonl_paths"]):
            candidates.append(session["target"] or f"codex:{session['id']}")
    candidates.extend(path for agent in AGENT_DIRS if agent != "codex" for path in iter_files(agent, None)
                      if target.lower() in os.path.basename(path).lower())
    if not candidates:
        raise ValueError(f"no session file matches '{target}'")
    if len(candidates) != 1:
        raise ValueError("multiple matches, narrow the id:\n" + "\n".join(candidates[:10]))
    if is_sqlite_session(candidates[0]):
        codex_sqlite.require_history(codex_home(), candidates[0].removeprefix("codex:"))
    return candidates[0]


def payload_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # Tool content may contain images or binary resources; do not dump them.
        parts = []
        for block in value:
            if isinstance(block, dict) and block.get("type") in TEXT_BLOCK_TYPES:
                parts.append(block.get("text") or "")
            else:
                parts.append("[non-text content omitted]")
        return "\n".join(parts)
    return json.dumps(value, ensure_ascii=False)


def tool_events(record):
    """Normalize supported call/result records; do not traverse nested tool output."""
    if record.get("isSidechain"):
        return
    if record.get("type") == "response_item":
        p = record.get("payload")
        if not isinstance(p, dict):
            return
        kind = p.get("type")
        if kind in ("function_call", "custom_tool_call"):
            yield 0, "call", p.get("call_id"), p.get("name", "unknown"), p.get("arguments", p.get("input", ""))
        elif kind in ("function_call_output", "custom_tool_call_output"):
            yield 0, "result", p.get("call_id"), "", p.get("output", "")
    elif record.get("type") in ("user", "assistant", "message"):
        message = record.get("message")
        if not isinstance(message, dict):
            return
        if message.get("role") == "toolResult":
            yield 0, "result", message.get("toolCallId"), message.get("toolName", ""), message.get("content", "")
            return
        content = message.get("content")
        if isinstance(content, list):
            for index, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "toolCall":
                    yield index, "call", block.get("id"), block.get("name", "unknown"), block.get("arguments", "")
                elif block.get("type") == "tool_use":
                    yield index, "call", block.get("id"), block.get("name", "unknown"), block.get("input", "")
                elif block.get("type") == "tool_result":
                    yield index, "result", block.get("tool_use_id"), "", block.get("content", "")


def read_tools(path, messages, turn):
    turns = {m["line"]: m["turn"] for m in messages}
    calls, results, current_turn = [], {}, None
    for line, record in iter_records(path):
        current_turn = turns.get(line, current_turn)
        for block, kind, call_id, name, value in tool_events(record):
            size = len(payload_text(value))
            if kind == "call" and current_turn == turn:
                calls.append({"id": f"c{line}.{block}", "call_id": call_id, "line": line,
                              "name": name, "input_chars": size})
            elif kind == "result" and call_id:
                results.setdefault(call_id, []).append((line, block, size))
    for call in calls:
        call["results"] = results.get(call["call_id"], []) if call["call_id"] else []
    return calls


def cmd_tools(path, message_id, call_selector, part, offset, n, max_chars):
    messages = read_messages(path)
    message = find_message(messages, message_id)
    if not message["turn"]:
        raise ValueError("no preceding user message; cannot determine this message's tool scope")
    calls = read_tools(path, messages, message["turn"])
    print(f"session: {path} | message: {message_id} | turn: {message['turn']}")
    if not call_selector:
        if offset > len(calls):
            raise ValueError(f"offset {offset} exceeds call count {len(calls)}")
        end = min(offset + n, len(calls))
        print(f"calls: {len(calls)} | shown: {offset}:{end} | next: " + (f"--offset {end}" if end < len(calls) else "none"))
        for call in calls[offset:end]:
            output_chars = sum(size for _, _, size in call["results"])
            state = "result-recorded" if call["results"] else "result-missing"
            print(f"[{call['id']}] {compress(call['name'], 100)} | input={call['input_chars']} chars | output={output_chars} chars | {state}")
        return
    call = next((c for c in calls if c["id"] == call_selector), None)
    if call is None:
        raise ValueError(f"call {call_selector} not found in {message['turn']}; use an ID from tools")
    if part == "output" and not call["results"]:
        raise ValueError("no matching result record; execution outcome is unverified")
    result_refs = {(line, block) for line, block, _ in call["results"]}
    result_lines = {line for line, _ in result_refs}
    pieces = []
    for line, record in iter_records(path):
        if (part == "input" and line != call["line"]) or (part == "output" and line not in result_lines):
            continue
        for block, kind, _, _, value in tool_events(record):
            if (part == "input" and kind == "call" and f"c{line}.{block}" == call_selector) or (part == "output" and (line, block) in result_refs):
                pieces.append(payload_text(value))
    print(f"call: {call_selector} | part: {part}")
    print_slice("\n".join(pieces), offset, max_chars)


ANCHOR_PATTERNS = {
    "commits": re.compile(r"\b[0-9a-f]{7,40}\b"),
    "branches": re.compile(r"(?:daily|feat|free-dev|hotfix|release|feature)/[\w.\-/]+"),
    "versions": re.compile(r"\b\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?\b"),
    "o2": re.compile(r"(?:iteration/|迭代|任务)\s*(\d{6,})"),
    "paths": re.compile(r"(?:/Users/\S+|\.worktrees/\S+|openspec/changes/[\w\-]+|src/pages/[\w\-/]+|frontend/[\w\-/]+|mono/[\w\-/]+)"),
    "mtop": re.compile(r"mtop\.[\w.]+"),
}


def _anchors(msgs):
    blob = "\n".join(t for _r, t in msgs)
    found = {}
    for name, pat in ANCHOR_PATTERNS.items():
        items = []
        for m in pat.finditer(blob):
            val = m.group(1) if name == "o2" and m.lastindex else m.group(0)
            val = val.rstrip(".,;:，。；：")
            if val and val not in items:
                items.append(val)
            if len(items) >= 15:
                break
        found[name] = items
    return found


LINK_TAG_RE = re.compile(r"\[\$[\w\-]+\]\([^)]*\)")
ACK_WORDS = {"继续", "可以", "ok", "okay", "好的", "好", "行", "是", "嗯", "对", "发", "1", "2", "3", "yes", "no"}
DECISION_KEYS = ("预发", "发布", "提交", "推送", "回滚", "修复", "修", "改", "测", "创建", "删", "不要", "别", "停", "继续", "开始", "发吧")


def _stripped(text):
    t = LINK_TAG_RE.sub("", text)
    return re.sub(r"\s+", "", t)


def _significant(text):
    t = _stripped(text)
    if not t or t in ACK_WORDS:
        return False
    if len(t) >= 8 or any(c in t for c in "?？!！"):
        return True
    return any(k in t for k in DECISION_KEYS)


def _select_users(users, keep_cap=80):
    idxs = set()
    for i, (_r, t) in enumerate(users):
        if i == 0 or i >= len(users) - 20 or _significant(t):
            idxs.add(i)
    idxs = sorted(idxs)
    if len(idxs) > keep_cap:
        idxs = sorted(set(list(range(0, 10)) + idxs[-70:]))
    return [users[i] for i in idxs], len(users)


def cmd_brief(path, user_max, last_max):
    msgs = extract_messages(path)
    if not msgs:
        print(f"error: no messages in {path}")
        return 1
    users = [(r, t) for r, t in msgs if r == "user"]
    assistants = [(r, t) for r, t in msgs if r == "assistant"]
    users, user_total = _select_users(users)
    anchors = _anchors(msgs)
    out = [f"# 会话续接简报 {os.path.basename(path)}（共 {len(msgs)} 条消息）", ""]
    if users:
        out += ["## 目标（首条用户消息）", "", compress(users[0][1].strip(), 400), ""]
    out += ["## 用户消息（保留 %d/%d 条，已过滤低信号）" % (len(users), user_total), ""]
    for _r, t in users:
        out.append("- " + compress(t.strip().replace("\n", " "), user_max))
    out += ["", "## 最后助手状态", ""]
    if assistants:
        out.append(compress(assistants[-1][1].strip(), last_max))
    else:
        out.append("（无助手消息）")
    out += ["", "## 锚点", ""]
    for name, items in anchors.items():
        out.append(f"- {name}: {', '.join(items) if items else '无'}")
    print("\n".join(out))
    return 0


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    listing = commands.add_parser("list", help="list recent local sessions")
    listing.add_argument("--agent", choices=AGENT_DIRS, required=True)
    listing.add_argument("--cwd")
    listing.add_argument("--limit", type=positive, default=10)
    listing.add_argument("--metadata-only", action="store_true", help="do not read dialogue previews")
    listing.add_argument("--count", action="store_true", help="print metadata counts without dialogue")
    for mode in ("tail", "show", "tools", "extract", "brief"):
        cmd = commands.add_parser(mode)
        cmd.add_argument("target", help="session file, codex:<thread-id>, or unique ID fragment")
        if mode in ("tail", "show", "tools", "extract"):
            cmd.add_argument("--max-chars", type=positive, default=160 if mode in ("tail", "extract") else 4000)
        if mode in ("show", "tools"):
            cmd.add_argument("--message", required=True, help="stable m<line> ID from tail")
            cmd.add_argument("--offset", type=nonnegative, default=0)
        if mode == "tail":
            cmd.add_argument("--n", type=positive, default=100)
            cmd.add_argument("--before", help="read older messages, excluding this m<line> ID")
            cmd.add_argument("--max-total-chars", type=positive, default=24000)
        elif mode == "tools":
            cmd.add_argument("--call", help="c<line>.<block> ID from the tools index")
            cmd.add_argument("--part", choices=("input", "output"), default="input")
            cmd.add_argument("--n", type=positive, default=20, help="calls per index page")
        elif mode == "extract":
            cmd.add_argument("--out", required=True, help="write full-history previews to a local file")
        elif mode == "brief":
            cmd.add_argument("--user-max", type=positive, default=120)
            cmd.add_argument("--last-max", type=positive, default=800)
    export = commands.add_parser("export", help="export an AI analysis JSONL view or dialogue Markdown")
    export.add_argument("target", help="session file, codex:<thread-id>, or unique ID fragment")
    export.add_argument("--format", dest="export_format", choices=("jsonl", "md"), default="jsonl")
    destination = export.add_mutually_exclusive_group()
    destination.add_argument("--out", help="exact output file; existing files are never overwritten")
    destination.add_argument("--output-dir", help="output directory; defaults to ~/Downloads")
    args = parser.parse_args(argv[1:])
    try:
        if args.mode == "list":
            cmd_list(args.agent, args.cwd, args.limit, args.metadata_only, args.count)
            return 0
        path = resolve_session(args.target)
        if args.mode == "tail":
            cmd_tail(path, args.n, args.before, args.max_chars, args.max_total_chars)
        elif args.mode == "show":
            cmd_show(path, args.message, args.offset, args.max_chars)
        elif args.mode == "tools":
            cmd_tools(path, args.message, args.call, args.part, args.offset, args.n, args.max_chars)
        elif args.mode == "extract":
            cmd_extract(path, args.out, args.max_chars)
        elif args.mode == "export":
            cmd_export(path, args.export_format, args.out, args.output_dir)
        elif args.mode == "brief":
            return cmd_brief(path, args.user_max, args.last_max)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
