# Watcher contract

The watcher is a bounded local process, not an LLM loop. It samples `herdr agent get`, records current state under `.artifacts/herdr-watch/`, and requests parent attention with `herdr agent prompt`. It never executes worker instructions or approves tools.

## Lifecycle

- `watching`: identities captured and checks active. Verify fresh heartbeatAt and expected watcherPid.
- `awaiting-start`: no new work observed; initial idle/done cannot complete a new assignment.
- `pending-parent`: notice retained because parent is busy or blocked.
- `notified`: terminal review prompt accepted, NOT task success or completed parent review.
- `stopped`: stop request observed and process exited.
- `failed` / `timed-out`: monitoring stopped; inspect error.

Pin both sessions by pane, terminal and agent-session ids. Session replacement stops the watcher. State sequence catches a fast task finishing between polls. Two matching terminal samples avoid transient-idle completion.

The public CLI has no expected-session/compare-and-set prompt option. The helper rechecks parent identity and idle status immediately before submission; Herdr also rejects blocked agents. A small check-to-submit race remains if a pane is reused concurrently. Delivery is best-effort, not race-free: stop the watcher before reusing either pane. Parent must revalidate the task rather than treat the notification as new authority.

Defaults: poll30s, parent inspection300s, lifetime3600s. Configure --poll-seconds / --inspect-seconds / --max-seconds for longer work; no infinite default. A busy parent may delay delivery until timeout; pending is not delivered.

## Failure/recovery

`status --job` reads the current record only. Stale heartbeat/dead PID means monitoring may have stopped, not that the worker completed. `stop --job` creates a request observed on the next sample, never kills a possibly reused PID.

One lock per parent/worker pair prevents duplicate watchers. Reclaim a stale lock only if its PID is no longer alive. Use a new job for a new assignment. Read-only query failures retry at most three consecutive samples. Session replacement or repeated failure stops monitoring and records why.

Failed or ambiguous parent-prompt calls are not retried automatically: the prompt might already have been submitted. Inspect the parent thread before replacing the watcher. Failures remain in the state/log and command result; no OS, sound or Herdr user-notification fallback is sent. Do not claim a closed or changed parent was awakened. The supervisor reports this limitation before an asynchronous handoff and checks the state on its next active inspection.

## Low-cost inspection

Parent reads short status/report first; inspect relevant recent pane output only if the report is missing or blocked. Review changed files and invalidated evidence only. Timers do not justify repository-wide scans, builds, full Figma exports or repeating valid checks.

Before ending an async handoff, report actual job/state. After terminal notification, verify exact changed files and result evidence, then report complete/partial/blocked. Stop or finish the watcher before reusing the pane for another task.
