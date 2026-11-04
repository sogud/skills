"""SQLite fixtures only: no real Codex database or personal sessions are used."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import codex_sqlite
import extract_conversation as reader


class CodexSqliteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-reader-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "codex-home"
        self.home.mkdir()
        previous = reader.AGENT_DIRS
        self.addCleanup(setattr, reader, "AGENT_DIRS", previous)
        reader.AGENT_DIRS = {agent: str(self.root / ("empty-" + agent)) for agent in previous}
        reader.AGENT_DIRS["codex"] = str(self.home / "sessions")
        for folder in reader.AGENT_DIRS.values():
            Path(folder).mkdir()
        self.state = self.home / "state_5.sqlite"
        self.history = self.home / "thread_history_1.sqlite"
        with contextlib.closing(sqlite3.connect(self.state)) as db, db:
            db.executescript("""
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY, cwd TEXT, rollout_path TEXT, source TEXT,
                    thread_source TEXT, updated_at_ms INTEGER, archived INTEGER,
                    title TEXT, first_user_message TEXT
                );
                CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT);
            """)
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)", [
                ("main-db", "/project", None, "vscode", "user", 9000, 0, "DO_NOT_READ_TITLE", "DO_NOT_READ_FIRST_MESSAGE"),
                ("child-db", "/project", None, json.dumps({"subagent": {"parent_thread_id": "main-db"}}), "subagent", 8000, 1, "CHILD_TITLE", "CHILD_FIRST"),
                ("meta-only", "/other", None, "cli", "user", 1000, 0, "META_TITLE", "META_FIRST"),
            ])
            db.execute("INSERT INTO thread_spawn_edges VALUES ('main-db','child-db')")
        with contextlib.closing(sqlite3.connect(self.history)) as db, db:
            db.execute("""CREATE TABLE thread_items (
                thread_id TEXT, item_id TEXT, item_type TEXT, rollout_ordinal INTEGER,
                created_at_ms INTEGER, updated_at_ordinal INTEGER, item_json TEXT,
                PRIMARY KEY (thread_id,item_id)
            )""")
        self.add_item("main-db", "user-1", 10, "userMessage", {"content": [{"type": "text", "text": "Question before compaction"}]}, 1000)
        self.add_item("main-db", "reasoning-1", 11, "reasoning", {"summary": ["PRIVATE_REASONING"]}, 1100)
        self.add_item("main-db", "exec-1", 15, "commandExecution", {
            "command": "PRIVATE_INPUT", "cwd": "/project", "status": "failed",
            "aggregatedOutput": "PRIVATE_OUTPUT", "exitCode": 1, "durationMs": 8,
        }, 2000)
        self.add_item("main-db", "compact-1", 20, "contextCompaction", {}, 2100)
        self.add_item("main-db", "answer-1", 25, "agentMessage", {"text": "Stored answer"}, 3000)
        self.add_item("child-db", "child-user", 3, "userMessage", {"content": [{"type": "text", "text": "child task"}]})
        self.add_item("child-db", "child-answer", 5, "agentMessage", {"text": "child answer"})
        self.add_item("history-only", "history-user", 1, "userMessage", {"content": [{"type": "text", "text": "old task"}]})
        self.add_item("history-only", "history-answer", 2, "agentMessage", {"text": "old answer"})

    def add_item(self, thread_id, item_id, ordinal, kind, data, created=4000):
        item = {"type": kind, "id": item_id, **data}
        with contextlib.closing(sqlite3.connect(self.history)) as db, db:
            db.execute("INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)", (
                thread_id, item_id, kind, ordinal, created, ordinal,
                json.dumps(item, ensure_ascii=False),
            ))

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = reader.main(["reader", *map(str, args)])
        return code, output.getvalue(), error.getvalue()

    def test_catalogue_counts_registry_history_and_children_without_body_reads(self):
        original_connect = codex_sqlite.connect
        def metadata_connection(path):
            db = original_connect(path)
            def authorize(action, table, column, _database, _trigger):
                if action == sqlite3.SQLITE_READ and (
                    (table == "thread_items" and column == "item_json") or
                    (table == "threads" and column in ["title", "first_user_message"])
                ):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(authorize)
            return db
        with mock.patch.object(codex_sqlite, "connect", side_effect=metadata_connection):
            with mock.patch.object(reader, "read_messages", side_effect=AssertionError("No dialogue reads while listing")):
                code, output, error = self.run_cli("list", "--agent", "codex", "--count")
                self.assertEqual(code, 0, error)
                counts = json.loads(output)
                self.assertEqual(counts["sessions"], 4)
                self.assertEqual(counts["registered"], 3)
                self.assertEqual(counts["main"], 2)
                self.assertEqual(counts["subagent"], 1)
                self.assertEqual(counts["unknown"], 1)
                self.assertEqual(counts["dialogue_indexed"], 3)
                self.assertEqual(counts["main_dialogue_indexed"], 1)
                self.assertEqual(counts["history_only"], 1)
                self.assertEqual(counts["metadata_only"], 1)
                code, output, error = self.run_cli("list", "--agent", "codex", "--metadata-only", "--cwd", "/project")
                self.assertEqual(code, 0, error)
                self.assertIn("codex:main-db", output)
                self.assertNotIn("meta-only", output)
                for hidden in ["DO_NOT_READ_TITLE", "DO_NOT_READ_FIRST_MESSAGE", "Question before compaction", "PRIVATE_INPUT"]:
                    self.assertNotIn(hidden, output)

    def test_jsonl_dedup_and_header_identity_prevent_wrong_thread_fallback(self):
        active = self.home / "sessions/active.jsonl"
        archive = self.home / "archived_sessions/archive.jsonl"
        archive.parent.mkdir()
        data = json.dumps({"type": "session_meta", "payload": {"id": "main-db", "cwd": "/project"}}) + "\n"
        active.write_text(data)
        archive.write_text(data)
        with contextlib.closing(sqlite3.connect(self.state)) as db, db:
            db.execute("UPDATE threads SET rollout_path=? WHERE id='main-db'", (str(active),))
            db.execute("UPDATE threads SET rollout_path=? WHERE id='meta-only'", (str(active),))
        sessions = codex_sqlite.catalogue(self.home)
        self.assertEqual(len(sessions), 4)
        main = next(row for row in sessions if row["id"] == "main-db")
        self.assertEqual(len(main["jsonl_paths"]), 2)
        self.assertEqual(main["target"], str(active))
        other = next(row for row in sessions if row["id"] == "meta-only")
        self.assertEqual(other["jsonl_paths"], [])
        self.assertIsNone(other["target"])
        self.assertEqual(reader.resolve_session("main-db"), str(active))
        self.assertEqual(reader.resolve_session("codex:main-db"), "codex:main-db")

    def test_sqlite_dialogue_export_and_tool_details_have_real_item_references(self):
        output = self.root / "analysis.jsonl"
        original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.state, self.history]}
        code, _, error = self.run_cli("export", "main-db", "--out", output)
        self.assertEqual(code, 0, error)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        header = rows[0]
        self.assertEqual(header["source"], "codex:main-db")
        self.assertEqual(header["source_kind"], "codex_sqlite")
        self.assertEqual(header["fingerprint_scope"], "stored_thread_items")
        self.assertEqual(header["source_database"], str(self.history))
        self.assertEqual(header["source_records"], 5)
        messages = [row for row in rows if row["type"] == "message"]
        self.assertEqual([row["text"] for row in messages], ["Question before compaction", "Stored answer"])
        self.assertEqual(messages[0]["id"], "m11")
        self.assertEqual(messages[0]["source_ref"]["item_id"], "user-1")
        self.assertEqual(messages[0]["timestamp"], 1000)
        indexed = next(row for row in rows if row["type"] == "tool_call")
        self.assertEqual(indexed["id"], "c16.0")
        self.assertEqual(indexed["message_id"], "m11")
        self.assertEqual(indexed["source_ref"]["rollout_ordinal"], 15)
        self.assertEqual(indexed["result_refs"][0]["block"], 1)
        self.assertTrue(indexed["has_result"])
        self.assertEqual(indexed["status"], "failed")
        for hidden in ["PRIVATE_INPUT", "PRIVATE_OUTPUT", "PRIVATE_REASONING", "DO_NOT_READ_TITLE"]:
            self.assertNotIn(hidden, output.read_text())
        code, detail, error = self.run_cli("tools", "codex:main-db", "--message", indexed["message_id"], "--call", indexed["id"], "--part", "output")
        self.assertEqual(code, 0, error)
        self.assertIn("PRIVATE_OUTPUT", detail)
        self.assertIn('"exitCode": 1', detail)
        code, detail, error = self.run_cli("tools", "codex:main-db", "--message", indexed["message_id"], "--call", indexed["id"], "--part", "input")
        self.assertEqual(code, 0, error)
        self.assertIn("PRIVATE_INPUT", detail)
        md = self.root / "dialogue.md"
        self.assertEqual(self.run_cli("export", "codex:main-db", "--format", "md", "--out", md)[0], 0)
        self.assertIn("Stored answer", md.read_text())
        for p, digest in original.items():
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest)

    def test_sqlite_default_exports_use_downloads_and_preserve_existing_files(self):
        home = self.root / "export-home"
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertEqual(self.run_cli("export", "codex:main-db")[0], 0)
            first = home / "Downloads/codex-main-db.analysis.jsonl"
            original = first.read_bytes()
            self.assertEqual(self.run_cli("export", "codex:main-db")[0], 0)
            self.assertEqual(first.read_bytes(), original)
            self.assertTrue((home / "Downloads/codex-main-db.analysis-2.jsonl").is_file())
            self.assertEqual(self.run_cli("export", "codex:main-db", "--format", "md")[0], 0)
            self.assertTrue((home / "Downloads/codex-main-db.simple.md").is_file())

    def test_selectors_survive_appending_items(self):
        before = reader.read_messages("codex:main-db")
        self.add_item("main-db", "next-answer", 40, "agentMessage", {"text": "next"}, 5000)
        code, output, error = self.run_cli("show", "codex:main-db", "--message", before[0]["id"])
        self.assertEqual(code, 0, error)
        self.assertIn("Question before compaction", output)
        self.assertEqual(reader.read_messages("codex:main-db")[0]["source_ref"], before[0]["source_ref"])

    def test_metadata_only_threads_and_bad_history_fail_without_empty_exports(self):
        output = self.root / "not-created.jsonl"
        code, _, error = self.run_cli("export", "codex:meta-only", "--out", output)
        self.assertEqual(code, 1)
        self.assertIn("no stored history items", error)
        self.assertFalse(output.exists())
        self.assertEqual(self.run_cli("export", "meta-only", "--out", output)[0], 1)
        self.add_item("main-db", "duplicate-ordinal", 15, "agentMessage", {"text": "duplicate"})
        code, _, error = self.run_cli("export", "codex:main-db", "--out", output)
        self.assertEqual(code, 1)
        self.assertIn("duplicate rollout ordinals", error)
        self.assertFalse(output.exists())

    def test_database_and_link_targets_cannot_be_overwritten(self):
        original = {p: p.read_bytes() for p in [self.state, self.history]}
        link = self.root / "history-link.jsonl"
        os.link(self.history, link)
        for target in [self.state, self.history, link]:
            code, _, error = self.run_cli("export", "codex:main-db", "--out", target)
            self.assertEqual(code, 1)
            self.assertIn("must not overwrite", error)
        for p, value in original.items():
            self.assertEqual(p.read_bytes(), value)
        with contextlib.closing(codex_sqlite.connect(self.history)) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM thread_items")

    def test_tool_projections_keep_only_saved_input_and_result_fields(self):
        samples = {
            "mcpToolCall": {"server": "fixture", "tool": "read", "arguments": {"path": "input"}, "result": {"content": [{"type": "text", "text": "output"}]}, "status": "completed"},
            "dynamicToolCall": {"tool": "inspect", "arguments": {"value": "input"}, "contentItems": [{"type": "text", "text": "output"}], "success": False},
            "fileChange": {"changes": [{"path": "fixture", "diff": "input"}], "status": "completed"},
            "webSearch": {"query": "input", "results": [{"url": "https://example.test"}]},
            "imageView": {"path": "input.png"},
            "imageGeneration": {"revisedPrompt": "input", "result": "output"},
            "collabAgentToolCall": {"tool": "spawnAgent", "prompt": "input", "agentsStates": {"fixture": "completed"}},
            "sleep": {"durationMs": 1},
        }
        for number, (kind, item) in enumerate(samples.items(), 100):
            self.add_item("main-db", kind, number, kind, item)
        summary, events = reader.build_analysis("codex:main-db")
        self.assertEqual(summary["tool_call_count"], 1 + len(samples))
        image = next(row for row in events if row.get("name") == "imageView")
        self.assertFalse(image["has_result"])
        for row in events:
            if row["type"] == "tool_call":
                self.assertNotIn("arguments", row)
                self.assertEqual(row["source_ref"]["database"], str(self.history))

    def test_unsupported_registry_schema_is_not_reported_as_empty(self):
        with contextlib.closing(sqlite3.connect(self.state)) as db, db:
            db.execute("DROP TABLE threads")
            db.execute("CREATE TABLE threads (title TEXT)")
        code, output, error = self.run_cli("list", "--agent", "codex", "--count")
        self.assertEqual(code, 1)
        self.assertIn("missing id", error)
        self.assertEqual(output, "")

    def test_missing_databases_use_jsonl_headers_and_missing_context_stays_unknown(self):
        self.state.unlink()
        self.history.unlink()
        path = self.home / "sessions/raw.jsonl"
        path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "raw-only", "cwd": "/raw"}}) + "\n")
        sessions = codex_sqlite.catalogue(self.home)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["target"], str(path))
        self.assertFalse(sessions[0]["has_history"])
        with self.assertRaisesRegex(ValueError, "not found"):
            reader.resolve_session("codex:raw-only")


if __name__ == "__main__":
    unittest.main()
