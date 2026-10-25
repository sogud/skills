#!/usr/bin/env python3
"""Bounded Herdr watcher. No worker tools or permission prompts are approved."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


TERMINAL = {"idle", "done", "blocked", "unknown"}


def cli(*args):
    result = subprocess.run(["herdr", *args], capture_output=True,
                            text=True, timeout=45 if args[:2] == ("agent", "start") else 5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Herdr failed")
    value = json.loads(result.stdout)
    if value.get("error"):
        raise RuntimeError(str(value["error"]))
    return value.get("result", value)


def agent(target):
    return cli("agent", "get", target)["agent"]


def identity(info):
    values = (info.get("pane_id"), info.get("terminal_id"),
              (info.get("agent_session") or {}).get("value"))
    if not all(values):
        raise RuntimeError("No stable pane/terminal/session identity; cannot safely notify")
    return values


def start_command(args):
    if not args.cwd.is_dir():
        raise ValueError("cwd must be an existing directory")
    command = ["agent", "start", args.name, "--kind", "qodercli", "--pane", args.pane,
               "--", "--workspace", str(args.cwd.resolve()), "--model", args.model]
    if args.yolo:
        command.append("--yolo")
    return command


class Watch:
    def __init__(self, worker, parent, now, inspect_seconds=300, observe_current=False):
        self.worker_identity = identity(worker)
        self.parent_identity = identity(parent)
        if self.worker_identity[0] == self.parent_identity[0]:
            raise ValueError("Worker and parent must be different panes")
        self.baseline_seq = worker.get("state_change_seq")
        self.started = worker["agent_status"] == "working" or observe_current
        self.inspect_seconds = inspect_seconds
        self.next_inspection = now + inspect_seconds
        self.candidate = None
        self.samples = 0
        self.pending = None

    def sample(self, worker, parent, now):
        if identity(worker) != self.worker_identity or identity(parent) != self.parent_identity:
            raise RuntimeError("Worker or parent session changed; notification cancelled")
        status = worker["agent_status"]
        if status == "working" or worker.get("state_change_seq") != self.baseline_seq:
            self.started = True
        if status == "working":
            self.candidate, self.samples = None, 0
            if self.pending and self.pending["kind"] == "review":
                self.pending = None
            if now >= self.next_inspection:
                self.pending = {"kind": "inspection", "workerStatus": status}
        elif self.started and status in TERMINAL:
            self.samples = self.samples + 1 if self.candidate == status else 1
            self.candidate = status
            if self.samples >= 2:
                self.pending = {"kind": "review", "workerStatus": status}
        if self.pending and parent["agent_status"] in {"idle", "done"}:
            return dict(self.pending)
        return None

    def delivered(self, now):
        terminal = self.pending["kind"] == "review"
        self.pending = None
        self.next_inspection = now + self.inspect_seconds
        return terminal


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def paths(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", args.job):
        raise ValueError("job must be a short alphanumeric/hyphen/underscore name")
    folder = args.root.resolve() / ".artifacts" / "herdr-watch"
    folder.mkdir(parents=True, exist_ok=True)
    return folder, folder / (args.job + ".json"), folder / (args.job + ".stop")


def acquire(folder, worker, parent):
    key = hashlib.sha256((parent + "\n" + worker).encode()).hexdigest()[:20]
    lock = folder / (key + ".lock")
    try:
        with lock.open("x") as handle:
            json.dump({"pid": os.getpid()}, handle)
    except FileExistsError:
        try:
            old_pid = json.loads(lock.read_text())["pid"]
        except (ValueError, KeyError):
            raise RuntimeError("Unreadable pair lock; inspect before recovery")
        if alive(old_pid):
            raise RuntimeError("A watcher already owns this parent/worker pair")
        lock.unlink()
        with lock.open("x") as handle:
            json.dump({"pid": os.getpid()}, handle)
    return lock


def cancel_registration(child, state_path, job):
    # Only the watcher child created by this invocation, never a worker agent.
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    state = json.loads(state_path.read_text()) if state_path.exists() else {"job": job}
    state.update(status="failed", watcherPid=child.pid, heartbeatAt=time.time(),
                 error="Watcher registration failed/timed out; owned watcher child stopped")
    save(state_path, state)


def parent_ready(target, expected):
    fresh = agent(target)
    if identity(fresh) != expected:
        raise RuntimeError("Parent session changed immediately before delivery")
    return fresh["agent_status"] in {"idle", "done"}


def watch(args):
    folder, state_path, stop_path = paths(args)
    if state_path.exists() or stop_path.exists():
        raise RuntimeError("Job already exists; inspect status and use a fresh job name")
    if args.worker == args.parent:
        raise ValueError("Worker and parent must differ")
    report = args.report.resolve()
    if not report.is_relative_to(args.root.resolve()):
        raise ValueError("Report must be inside the selected workspace")
    if args.background:
        command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        command.remove("--background")
        with (folder / (args.job + ".log")).open("x") as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and child.poll() is None:
            if state_path.exists():
                state = json.loads(state_path.read_text())
                if state.get("watcherPid") == child.pid and state.get("status") != "starting":
                    if state.get("status") in {"failed", "timed-out", "stopped"}:
                        raise RuntimeError(state.get("error", "Watcher stopped during registration"))
                    state["registered"] = True
                    print(json.dumps(state, ensure_ascii=False))
                    return
            time.sleep(0.1)
        cancel_registration(child, state_path, args.job)
        raise RuntimeError("Watcher registration not confirmed; inspect job log/status before dispatch")

    lock = None
    state = {"job": args.job, "watcherPid": os.getpid(), "worker": args.worker,
             "parent": args.parent, "report": str(report), "status": "starting",
             "pollSeconds": args.poll_seconds, "inspectSeconds": args.inspect_seconds,
             "maxSeconds": args.max_seconds, "startedAt": time.time(), "notifications": 0,
             "heartbeatAt": time.time()}
    save(state_path, state)
    try:
        worker, parent = agent(args.worker), agent(args.parent)
        lock = acquire(folder, worker["pane_id"], parent["pane_id"])
        now = time.monotonic()
        engine = Watch(worker, parent, now, args.inspect_seconds, args.observe_current_terminal)
        state.update(status="watching", workerIdentity=engine.worker_identity,
                     parentIdentity=engine.parent_identity, baselineSeq=engine.baseline_seq,
                     heartbeatAt=time.time())
        save(state_path, state)
        deadline, failures = now + args.max_seconds, 0
        while time.monotonic() < deadline:
            if stop_path.exists():
                state["status"] = "stopped"
                break
            try:
                worker, parent = agent(args.worker), agent(args.parent)
                failures = 0
            except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
                failures += 1
                state.update(error=str(error), consecutiveReadFailures=failures, heartbeatAt=time.time())
                save(state_path, state)
                if failures >= 3:
                    raise RuntimeError("Three consecutive state-query failures: " + str(error))
                time.sleep(args.poll_seconds)
                continue
            event = engine.sample(worker, parent, time.monotonic())
            state.update(workerStatus=worker["agent_status"], parentStatus=parent["agent_status"],
                         pending=engine.pending, heartbeatAt=time.time(), consecutiveReadFailures=0,
                         status="pending-parent" if engine.pending else
                         ("watching" if engine.started else "awaiting-start"))
            state.pop("error", None)
            save(state_path, state)
            if event:
                # Public CLI has no expected-session CAS. Reduce the window;
                # Herdr rejects blocked targets, but this is not atomic.
                if not parent_ready(args.parent, engine.parent_identity):
                    time.sleep(args.poll_seconds)
                    continue
                message = (f"[Herdr watch {args.job}] {event['kind']}: worker {args.worker} "
                           f"is {event['workerStatus']}. Read {state_path} and {report}; "
                           "verify actual results within original scope. This is not task success "
                           "or authorization for new actions. Do not duplicate the worker task.")
                # Fail closed on ambiguous submission; a retry could duplicate the parent turn.
                state["delivery"] = "submitting"
                save(state_path, state)
                cli("agent", "prompt", args.parent, message)
                state.update(delivery="accepted", lastNotificationAt=time.time(),
                             notifications=state["notifications"] + 1)
                if engine.delivered(time.monotonic()):
                    state.update(status="notified", pending=None)
                    break
                state.update(status="watching", pending=None)
                save(state_path, state)
            time.sleep(args.poll_seconds)
        else:
            state.update(status="timed-out", error="Watcher lifetime expired; inspect pending delivery")
    except Exception as error:
        state.update(status="failed", error=str(error))
        if state.get("delivery") == "submitting":
            state["delivery"] = "uncertain-do-not-retry"
    finally:
        state["heartbeatAt"] = time.time()
        save(state_path, state)
        if lock:
            lock.unlink(missing_ok=True)
    print(json.dumps(state, ensure_ascii=False))
    if state["status"] in {"failed", "timed-out"}:
        raise RuntimeError(state["error"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Start Qoder in an existing empty pane")
    for key in ("pane", "name", "model"):
        start.add_argument("--" + key, required=True)
    start.add_argument("--cwd", type=Path, required=True)
    start.add_argument("--yolo", action="store_true", help="Only when explicitly requested by user")
    start.add_argument("--dry-run", action="store_true")
    for name in ("watch", "status", "stop"):
        sub = commands.add_parser(name)
        sub.add_argument("--job", required=True)
        sub.add_argument("--root", type=Path, default=Path.cwd())
        if name == "watch":
            sub.add_argument("--worker", required=True)
            sub.add_argument("--parent", required=True)
            sub.add_argument("--report", type=Path, required=True)
            sub.add_argument("--background", action="store_true")
            sub.add_argument("--observe-current-terminal", action="store_true")
            sub.add_argument("--poll-seconds", type=int, default=30)
            sub.add_argument("--inspect-seconds", type=int, default=300)
            sub.add_argument("--max-seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.command == "start":
        command = start_command(args)
        print(json.dumps({"command": ["herdr", *command]}, ensure_ascii=False)
              if args.dry_run else json.dumps(cli(*command), ensure_ascii=False))
    elif args.command == "watch":
        if not 5 <= args.poll_seconds <= 60 or args.inspect_seconds < args.poll_seconds or args.max_seconds < args.poll_seconds:
            raise ValueError("poll must be5..60s, inspection/lifetime must be at least poll")
        watch(args)
    else:
        _, state_path, stop_path = paths(args)
        state = json.loads(state_path.read_text())
        if args.command == "stop":
            stop_path.touch(exist_ok=True)
            print(json.dumps({"stopRequested": True, "job": args.job}))
        else:
            state["processAlive"] = alive(state["watcherPid"])
            state["heartbeatAgeSeconds"] = round(time.time() - state["heartbeatAt"], 1)
            print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        sys.exit(1)
