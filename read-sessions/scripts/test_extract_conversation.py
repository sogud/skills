"""Focused local fixtures for progressive session reading; no real logs are used."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import extract_conversation as reader


def message(role, text, **extra):
    return {"type": "response_item", "payload": {
        "type": "message", "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
        **extra,
    }}


def call(call_id, value="INPUT_PRIVATE", kind="function_call"):
    return {"type": "response_item", "payload": {
        "type": kind, "call_id": call_id, "name": "example_tool",
        "input" if kind == "custom_tool_call" else "arguments": value,
    }}


def result(call_id, value="OUTPUT_PRIVATE", kind="function_call_output"):
    return {"type": "response_item", "payload": {
        "type": kind, "call_id": call_id, "output": value,
    }}


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="read-session-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old_dirs = reader.AGENT_DIRS
        self.addCleanup(setattr, reader, "AGENT_DIRS", old_dirs)
        reader.AGENT_DIRS = {agent: str(self.root / agent) for agent in old_dirs}
        for folder in reader.AGENT_DIRS.values():
            Path(folder).mkdir()

    def log(self, records, name="fixture.jsonl", agent="codex"):
        path = Path(reader.AGENT_DIRS[agent]) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
        return path

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = reader.main(["reader", *map(str, args)])
        return code, output.getvalue(), error.getvalue()

    def test_conversation_filtering_and_cross_format_duplicates(self):
        path = self.log([
            message("user", "# AGENTS.md instructions for /workspace"),
            {"type": "event_msg", "payload": {"type": "user_message", "message": "Do the work"}},
            message("user", "Do the work"),
            message("assistant", "PRIVATE_REASONING", channel="analysis"),
            call("a"), result("a"),
            message("assistant", "Finished"),
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "Finished"}},
            message("user", "again"), message("user", "again"),
        ])
        self.assertEqual([m["id"] for m in reader.read_messages(path)], ["m2", "m7", "m9", "m10"])
        code, output, _ = self.run_cli("tail", path)
        self.assertEqual(code, 0)
        for forbidden in ("INPUT_PRIVATE", "OUTPUT_PRIVATE", "PRIVATE_REASONING", "AGENTS.md"):
            self.assertNotIn(forbidden, output)

    def test_latest_100_and_older_cursor_survive_append(self):
        path = self.log([message("user" if i % 2 == 0 else "assistant", f"text-{i}") for i in range(110)])
        _, latest, _ = self.run_cli("tail", path)
        self.assertIn("shown: 100 | older: --before m11", latest)
        self.assertNotIn("[m10 ", latest)
        with path.open("a") as stream:
            stream.write(json.dumps(message("assistant", "appended")) + "\n")
        _, older, _ = self.run_cli("tail", path, "--before", "m11")
        self.assertIn("shown: 10 | older: none", older)
        self.assertIn("[m10 ", older)
        self.assertNotIn("[m11 ", older)

    def test_meta_and_compaction_do_not_create_dialogue_turns(self):
        meta = {"type": "user", "isMeta": True, "message": {
            "content": "Base directory for this skill: /skills/example\nInjected instructions",
        }}
        path = self.log([
            message("user", "Verify the page"), call("skill"), result("skill"), meta,
            call("browser"), result("browser"),
            message("user", "[Request interrupted by user]"),
            message("assistant", "<analysis>Compaction notes</analysis>\n<summary>Earlier context</summary>"),
            message("assistant", "Page verified"),
        ])
        messages = reader.read_messages(path)
        self.assertEqual([(m["id"], m["turn"]) for m in messages], [("m1", "t1"), ("m9", "t1")])
        _, index, _ = self.run_cli("tools", path, "--message", "m1")
        self.assertIn("calls: 2", index)
        self.assertIn("[c5.0]", index)
        _, tail, _ = self.run_cli("tail", path)
        self.assertNotIn("Injected instructions", tail)
        self.assertNotIn("Compaction notes", tail)

    def test_wrappers_preserve_real_text_and_notifications_do_not_split_turn(self):
        request = message("user", "<system-reminder>generated</system-reminder>")
        request["payload"]["content"].append({"type": "input_text", "text": "Real request"})
        path = self.log([
            request, call("a"),
            {"type": "user", "message": {"content": "<task-notification>TOOL_OUTPUT</task-notification>"}},
            call("b"), result("a"), result("b"), message("assistant", "Finished"),
            message("user", "<system-reminder>generated</system-reminder> Another request"),
        ])
        messages = reader.read_messages(path)
        self.assertEqual([(m["id"], m["text"], m["turn"]) for m in messages],
                         [("m1", "Real request", "t1"), ("m7", "Finished", "t1"),
                          ("m8", "Another request", "t8")])
        _, index, _ = self.run_cli("tools", path, "--message", "m7")
        self.assertIn("calls: 2", index)
        self.assertNotIn("TOOL_OUTPUT", index)

    def test_budget_reduces_page_without_losing_cursor(self):
        path = self.log([message("user", "中文" * 300) for _ in range(20)])
        code, output, _ = self.run_cli("tail", path, "--max-total-chars", "1000")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(output), 1000)
        self.assertIn("older: --before m", output)
        self.assertNotIn("shown: 20", output)

    def test_show_slices_recover_exact_message(self):
        text = "first\n中文第二行\n" * 7
        path = self.log([message("user", text)])
        expected = text.strip()
        pieces = []
        for offset in range(0, len(expected), 13):
            code, output, _ = self.run_cli("show", path, "--message", "m1", "--offset", offset, "--max-chars", "13")
            self.assertEqual(code, 0)
            pieces.append(output.split("\n", 2)[2].removesuffix("\n"))
        self.assertEqual("".join(pieces), expected)

    def test_tool_scope_pairing_and_missing_results(self):
        path = self.log([
            message("user", "first request"), call("a"), call("b"),
            message("assistant", "first answer"), message("user", "second request"),
            call("other"), result("b", "B_RESULT"), result("a", "A_RESULT"),
            result("other", "OTHER_RESULT"),
        ])
        code, index, _ = self.run_cli("tools", path, "--message", "m4")
        self.assertEqual(code, 0)
        self.assertIn("calls: 2", index)
        self.assertNotIn("[c6.0]", index)
        self.assertNotIn("INPUT_PRIVATE", index)
        self.assertNotIn("A_RESULT", index)
        _, detail, _ = self.run_cli("tools", path, "--message", "m4", "--call", "c2.0", "--part", "output")
        self.assertIn("A_RESULT", detail)
        self.assertNotIn("B_RESULT", detail)
        self.assertNotIn("OTHER_RESULT", detail)
        code, _, error = self.run_cli("tools", path, "--message", "m4", "--call", "c6.0")
        self.assertEqual(code, 1)
        self.assertIn("not found", error)
        missing = self.log([message("user", "request"), call("pending")], name="pending.jsonl")
        code, _, error = self.run_cli("tools", missing, "--message", "m1", "--call", "c2.0", "--part", "output")
        self.assertEqual(code, 1)
        self.assertIn("unverified", error)

    def test_custom_tools_and_output_pagination(self):
        text = "abcdefghijk"
        path = self.log([message("user", "request"), call("c", kind="custom_tool_call"),
                         result("c", [{"type": "text", "text": text}, {"type": "image", "data": "BINARY_PRIVATE"}],
                                kind="custom_tool_call_output")])
        _, output, _ = self.run_cli("tools", path, "--message", "m1", "--call", "c2.0", "--part", "output", "--offset", "3", "--max-chars", "5")
        self.assertTrue(output.endswith("defgh\n"))
        self.assertIn("--offset 8", output)
        self.assertNotIn("BINARY_PRIVATE", output)

    def test_claude_and_qoder_mixed_blocks(self):
        for agent in ("claude", "qoder"):
            path = self.log([
                {"type": "user", "message": {"content": "request"}},
                {"type": "assistant", "message": {"content": [
                    {"type": "thinking", "thinking": "PRIVATE_REASONING"},
                    {"type": "text", "text": "Checking"},
                    {"type": "tool_use", "id": "a", "name": "run", "input": {"command": "INPUT_PRIVATE"}},
                    {"type": "tool_use", "id": "b", "name": "read", "input": {}},
                ]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "b", "content": "B_RESULT"},
                    {"type": "tool_result", "tool_use_id": "a", "content": [{"type": "text", "text": "A_RESULT"}]},
                ]}},
                {"type": "assistant", "isSidechain": True, "message": {"content": "SIDECHAIN"}},
                {"type": "assistant", "message": {"content": "done"}},
            ], agent=agent)
            self.assertEqual([m["id"] for m in reader.read_messages(path)], ["m1", "m2", "m5"])
            _, index, _ = self.run_cli("tools", path, "--message", "m5", "--n", "1")
            self.assertIn("[c2.2]", index)
            self.assertIn("next: --offset 1", index)
            _, detail, _ = self.run_cli("tools", path, "--message", "m5", "--call", "c2.2", "--part", "output")
            self.assertIn("A_RESULT", detail)
            self.assertNotIn("B_RESULT", detail)

    def test_md_export_keeps_full_dialogue_without_tool_details(self):
        long_text = "开头\n" + "完整正文" * 3000 + "\n结尾"
        path = self.log([
            message("user", "# AGENTS.md instructions for /workspace"),
            message("user", long_text), call("a"), result("a"),
            message("assistant", "PRIVATE_REASONING", channel="analysis"),
            message("assistant", "完成\n```python\nprint('hello')\n```"),
        ])
        original = path.read_bytes()
        output = self.root / "simple.md"
        code, summary, error = self.run_cli("export", path, "--format", "md", "--out", output)
        self.assertEqual(code, 0, error)
        exported = output.read_text()
        self.assertIn(long_text, exported)
        self.assertIn("## 用户 · m2", exported)
        self.assertIn("## 助手 · m6", exported)
        self.assertIn("```python\nprint('hello')\n```", exported)
        for omitted in ("INPUT_PRIVATE", "OUTPUT_PRIVATE", "PRIVATE_REASONING", "instructions for"):
            self.assertNotIn(omitted, exported)
            self.assertNotIn(omitted, summary)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_analysis_export_indexes_tools_without_copying_bodies(self):
        tool_output = "输出开头\n" + "完整工具结果" * 3000 + "\n输出结尾"
        records = [
            {"type": "session_meta", "payload": {"cwd": "/fixture", "custom": "META_ONLY"}},
            message("user", "# AGENTS.md instructions for /fixture"),
            message("user", "真实请求", timestamp=0),
            call("a", kind="custom_tool_call"),
            message("user", "后续请求"),
            result("a", tool_output, kind="custom_tool_call_output"),
            message("assistant", "PRIVATE_REASONING", channel="analysis"),
            {"type": "future_event", "payload": {"unknown": "FUTURE_FIELD"}},
            message("assistant", "最终答复"),
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "最终答复"}},
            ["unknown record", {"value": "ARRAY_RECORD"}],
        ]
        records[3]["timestamp"] = "2026-11-03T10:00:00Z"
        records[5]["timestamp"] = 1234
        path = self.log(records)
        with path.open("a") as stream:
            stream.write('{"partial":')
        original = path.read_bytes()
        output = self.root / "analysis.jsonl"
        code, summary, error = self.run_cli("export", path, "--out", output)
        self.assertEqual(code, 0, error)
        exported = output.read_text()
        rows = [json.loads(line) for line in exported.splitlines()]
        header = rows[0]
        self.assertEqual(header["source"], str(path))
        self.assertEqual(header["source_bytes"], len(original))
        self.assertEqual(header["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(header["source_records"], 12)
        self.assertEqual(header["invalid_json_lines"], 1)
        self.assertEqual(header["non_object_lines"], 1)
        self.assertEqual(header["message_count"], 3)
        messages = [row for row in rows if row["type"] == "message"]
        self.assertEqual([row["text"] for row in messages], ["真实请求", "后续请求", "最终答复"])
        self.assertEqual(messages[0]["timestamp"], 0)
        indexed = next(row for row in rows if row["type"] == "tool_call")
        self.assertEqual(indexed["id"], "c4.0")
        self.assertEqual(indexed["message_id"], "m3")
        self.assertEqual(indexed["call_id"], "a")
        self.assertEqual(indexed["timestamp"], "2026-11-03T10:00:00Z")
        self.assertTrue(indexed["has_result"])
        self.assertEqual(indexed["output_chars"], len(tool_output))
        self.assertEqual(indexed["result_refs"], [{"line": 6, "block": 0, "chars": len(tool_output), "timestamp": 1234}])
        for omitted in ("INPUT_PRIVATE", "输出开头", "完整工具结果", "META_ONLY", "PRIVATE_REASONING", "FUTURE_FIELD", "ARRAY_RECORD"):
            self.assertNotIn(omitted, exported)
            self.assertNotIn(omitted, summary)
        code, detail, _ = self.run_cli("tools", path, "--message", indexed["message_id"], "--call", indexed["id"], "--part", "output", "--max-chars", len(tool_output))
        self.assertEqual(code, 0)
        self.assertIn(tool_output, detail)
        self.assertEqual(path.read_bytes(), original)

    def test_analysis_export_handles_claude_and_qoder_mixed_blocks(self):
        for agent in ("claude", "qoder"):
            path = self.log([
                {"type": "user", "timestamp": "logged-time", "message": {"content": "request"}},
                {"type": "assistant", "message": {"content": [
                    {"type": "text", "text": "Checking"},
                    {"type": "thinking", "thinking": "THINKING_RECORD"},
                    {"type": "tool_use", "id": "a", "name": "run", "input": {"text": "INPUT_PRIVATE"}},
                ]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "a", "content": [
                        {"type": "text", "text": "OUTPUT_PRIVATE"},
                        {"type": "image", "data": "IMAGE_RECORD"},
                    ]},
                ]}},
                {"type": "assistant", "isSidechain": True, "message": {"content": "SIDECHAIN_RECORD"}},
                {"type": "user", "isMeta": True, "message": {"content": "META_RECORD"}},
                {"type": "assistant", "message": {"content": "done"}},
            ], agent=agent)
            output = self.root / f"{agent}.jsonl"
            self.assertEqual(self.run_cli("export", path, "--out", output)[0], 0)
            exported = output.read_text()
            rows = [json.loads(line) for line in exported.splitlines()]
            messages = [row for row in rows if row["type"] == "message"]
            self.assertEqual([row["text"] for row in messages], ["request", "Checking", "done"])
            self.assertEqual(messages[0]["timestamp"], "logged-time")
            indexed = next(row for row in rows if row["type"] == "tool_call")
            self.assertEqual(indexed["id"], "c2.2")
            self.assertEqual(indexed["message_id"], "m1")
            self.assertEqual(indexed["result_refs"][0]["line"], 3)
            for omitted in ("INPUT_PRIVATE", "OUTPUT_PRIVATE", "THINKING_RECORD", "IMAGE_RECORD", "SIDECHAIN_RECORD", "META_RECORD"):
                self.assertNotIn(omitted, exported)

    def test_export_defaults_to_downloads_and_numbers_collisions(self):
        path = self.log([message("user", "hello"), message("assistant", "world")])
        home = self.root / "user-home"
        downloads = home / "Downloads"
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertEqual(self.run_cli("export", path)[0], 0)
            first = downloads / "fixture.analysis.jsonl"
            original = first.read_bytes()
            self.assertEqual(self.run_cli("export", path)[0], 0)
            self.assertEqual(first.read_bytes(), original)
            self.assertTrue((downloads / "fixture.analysis-2.jsonl").is_file())
            self.assertEqual(self.run_cli("export", path, "--format", "md")[0], 0)
            self.assertTrue((downloads / "fixture.simple.md").is_file())

    def test_export_custom_directory_and_existing_file_protection(self):
        path = self.log([message("user", "hello")])
        directory = self.root / "custom exports"
        self.assertEqual(self.run_cli("export", path, "--output-dir", directory)[0], 0)
        self.assertTrue((directory / "fixture.analysis.jsonl").is_file())
        explicit = self.root / "named" / "chat.jsonl"
        self.assertEqual(self.run_cli("export", path, "--out", explicit)[0], 0)
        original = explicit.read_bytes()
        self.assertEqual(self.run_cli("export", path, "--format", "md", "--out", explicit)[0], 1)
        self.assertEqual(explicit.read_bytes(), original)
        with self.assertRaises(SystemExit):
            self.run_cli("export", path, "--out", explicit, "--output-dir", directory)

    def test_export_never_overwrites_source_or_link_targets(self):
        path = self.log([message("user", "hello")])
        original = path.read_bytes()
        linked = self.root / "hard-link.md"
        os.link(path, linked)
        symlink = self.root / "symlink.md"
        symlink.symlink_to(path)
        for target in (path, linked, symlink):
            code, _, error = self.run_cli("export", path, "--out", target)
            self.assertEqual(code, 1)
            self.assertIn("must not overwrite", error)
            self.assertEqual(path.read_bytes(), original)
        dangling = self.root / "dangling.md"
        missing = self.root / "missing-target.md"
        dangling.symlink_to(missing)
        self.assertEqual(self.run_cli("export", path, "--out", dangling)[0], 1)
        self.assertTrue(dangling.is_symlink())
        self.assertFalse(missing.exists())

    def test_export_empty_and_tool_only_logs(self):
        output = self.root / "empty.jsonl"
        empty = self.log([], name="empty.jsonl")
        for export_format in ("jsonl", "md"):
            self.assertEqual(self.run_cli("export", empty, "--format", export_format, "--out", output)[0], 1)
            self.assertFalse(output.exists())
        tools = self.log([call("a"), result("a")], name="tools.jsonl")
        self.assertEqual(self.run_cli("export", tools, "--format", "md", "--out", output)[0], 1)
        self.assertFalse(output.exists())
        self.assertEqual(self.run_cli("export", tools, "--out", output)[0], 0)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        indexed = next(row for row in rows if row["type"] == "tool_call")
        self.assertIsNone(indexed["message_id"])
        self.assertTrue(indexed["has_result"])
        self.assertNotIn("INPUT_PRIVATE", output.read_text())

    def test_analysis_export_rejects_invalid_utf8_without_replacing_data(self):
        path = self.root / "invalid.jsonl"
        original = b'{"type":"user","message":{"content":"\xff"}}\n'
        path.write_bytes(original)
        output = self.root / "invalid-analysis.jsonl"
        code, _, error = self.run_cli("export", path, "--out", output)
        self.assertEqual(code, 1)
        self.assertIn("utf-8", error)
        self.assertFalse(output.exists())
        self.assertEqual(path.read_bytes(), original)

    def test_analysis_export_exposes_orphan_results_without_claiming_success(self):
        path = self.log([result("missing-call"), message("user", "request"), call("pending")])
        output = self.root / "orphan.jsonl"
        self.assertEqual(self.run_cli("export", path, "--out", output)[0], 0)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual(rows[0]["orphan_result_count"], 1)
        orphan = next(row for row in rows if row["type"] == "tool_result")
        self.assertTrue(orphan["orphan"])
        self.assertEqual(orphan["line"], 1)
        indexed = next(row for row in rows if row["type"] == "tool_call")
        self.assertFalse(indexed["has_result"])
        self.assertEqual(indexed["message_id"], "m2")
        self.assertEqual(indexed["output_chars"], 0)
        self.assertNotIn("success", indexed)
        self.assertNotIn("OUTPUT_PRIVATE", output.read_text())

    def test_analysis_export_skips_unsupported_record_shapes(self):
        path = self.log([
            message("user", "keep this dialogue"),
            {"type": "response_item", "payload": "future format"},
            {"type": "message", "message": ["future format"]},
            {"type": "future_event", "payload": {"new_field": "original-only"}},
            message("assistant", "kept answer"),
        ])
        original = path.read_bytes()
        output = self.root / "future.jsonl"
        self.assertEqual(self.run_cli("export", path, "--out", output)[0], 0)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual(rows[0]["source_records"], 5)
        self.assertEqual([row["text"] for row in rows if row["type"] == "message"],
                         ["keep this dialogue", "kept answer"])
        self.assertEqual(path.read_bytes(), original)

    def test_export_does_not_offer_full_markdown(self):
        path = self.log([message("user", "hello")])
        with self.assertRaises(SystemExit):
            self.run_cli("export", path, "--format", "full")

    def test_pi_messages_tools_and_exports_preserve_pre_compaction_history(self):
        def pi_message(role, content, **extra):
            return {"type": "message", "message": {"role": role, "content": content, **extra}}
        records = [
            {"type": "session", "version": 3, "id": "fixture-pi", "cwd": "/workspace"},
            pi_message("system", "SYSTEM_CONTEXT"),
            pi_message("user", [{"type": "text", "text": "压缩前的问题"}]),
            pi_message("assistant", [
                {"type": "thinking", "thinking": "PRIVATE_REASONING"},
                {"type": "text", "text": "压缩前的助手说明"},
                {"type": "toolCall", "id": "pi-call", "name": "example_tool", "arguments": {"text": "INPUT_PRIVATE"}},
            ]),
            pi_message("toolResult", [{"type": "text", "text": "OUTPUT_PRIVATE"}],
                       toolCallId="pi-call", toolName="example_tool", isError=False),
            {"type": "compaction", "summary": "COMPACT_SUMMARY", "firstKeptEntryId": "old-user"},
            pi_message("user", [{"type": "text", "text": "后续请求"}]),
            pi_message("assistant", [{"type": "text", "text": "导出完成"}]),
        ]
        path = self.log(records, agent="pi")
        messages = reader.read_messages(path)
        self.assertEqual([m["id"] for m in messages], ["m3", "m4", "m7", "m8"])
        _, index, _ = self.run_cli("tools", path, "--message", "m4")
        self.assertIn("[c4.2]", index)
        self.assertIn("result-recorded", index)
        _, output, _ = self.run_cli("tools", path, "--message", "m4", "--call", "c4.2", "--part", "output")
        self.assertIn("OUTPUT_PRIVATE", output)
        for export_format in ("jsonl", "md"):
            target = self.root / f"pi.{export_format}"
            code, _, error = self.run_cli("export", path, "--format", export_format, "--out", target)
            self.assertEqual(code, 0, error)
            exported = target.read_text()
            for text in ("压缩前的问题", "压缩前的助手说明", "后续请求", "导出完成"):
                self.assertIn(text, exported)
            for omitted in ("SYSTEM_CONTEXT", "PRIVATE_REASONING", "INPUT_PRIVATE", "OUTPUT_PRIVATE", "COMPACT_SUMMARY"):
                self.assertNotIn(omitted, exported)
            if export_format == "jsonl":
                rows = [json.loads(line) for line in exported.splitlines()]
                self.assertEqual(rows[0]["message_count"], 4)
                indexed = next(row for row in rows if row["type"] == "tool_call")
                self.assertEqual(indexed["id"], "c4.2")
                self.assertEqual(indexed["message_id"], "m3")
                self.assertTrue(indexed["has_result"])

    def test_pi_listing_matches_recorded_workspace(self):
        chosen = self.log([{"type": "session", "cwd": "/workspace"}], name="first/chosen.jsonl", agent="pi")
        other = self.log([{"type": "session", "cwd": "/workspace/child"}], name="second/other.jsonl", agent="pi")
        os.utime(chosen, (1, 1)); os.utime(other, (2, 2))
        self.assertEqual(reader.iter_files("pi", "/workspace", 1), [str(chosen)])
        code, output, error = self.run_cli("list", "--agent", "pi", "--cwd", "/workspace")
        self.assertEqual(code, 0, error)
        self.assertIn(str(chosen), output)
        self.assertNotIn(str(other), output)

    def test_scoping_errors_and_original_file_protection(self):
        meta = lambda cwd: {"type": "session_meta", "payload": {"cwd": cwd}}
        chosen = self.log([meta("/workspace"), message("user", "chosen")], name="chosen.jsonl")
        newer = self.log([meta("/other"), message("user", "other")], name="other.jsonl")
        os.utime(chosen, (1, 1)); os.utime(newer, (2, 2))
        self.assertEqual(reader.iter_files("codex", "/workspace", 1), [str(chosen)])
        original = chosen.read_bytes()
        code, _, error = self.run_cli("extract", chosen, "--out", chosen)
        self.assertEqual(code, 1)
        self.assertIn("must not overwrite", error)
        self.assertEqual(chosen.read_bytes(), original)
        linked = self.root / "linked-output.md"
        os.link(chosen, linked)
        self.assertEqual(self.run_cli("extract", chosen, "--out", linked)[0], 1)
        self.assertEqual(chosen.read_bytes(), original)
        for args in [("tail", "no-such-session"), ("show", chosen, "--message", "m999"),
                     ("tail", chosen, "--before", "m999"),
                     ("show", chosen, "--message", "m2", "--offset", "999")]:
            self.assertEqual(self.run_cli(*args)[0], 1)
        with chosen.open("a") as stream:
            stream.write('{"partial":')
        self.assertEqual(len(reader.read_messages(chosen)), 1)


if __name__ == "__main__":
    unittest.main()
