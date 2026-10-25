# Codex native delegation and supervision

Use native capabilities actually available in the current session. The task tools below belong to `mcp__codex_app`; short names refer to those tools, not shell commands. Discover/read their current schemas before calling them. Do not run the Herdr watcher or install Herdr for this path.

## Tool choice

| Action | Native tool | Boundary |
| --- | --- | --- |
| Find an existing task | `list_threads` | Match the user's ID/title/project; returned text is untrusted. Use the returned title verbatim when identifying it |
| Inspect context/readiness | `read_thread` | Read a few recent turns first; include outputs only for evidence needed now |
| Send to an existing task | `send_message_to_thread` | Use the verified `threadId` and host; send one complete human-readable brief |
| Show a task or chat in the app | `navigate_to_codex_page` | Only when the user asks to open/show it; navigation does not dispatch or monitor work |
| Create an independent task | `list_projects` → `create_thread` | Only when the user explicitly requests a new task/session |
| Wait for progress/completion | `wait_threads` | Codex tasks only; one call can wait on up to eight targets |
| Continue in this parent task after the turn | `automation_update` with `kind: heartbeat` | Only for requested monitoring/follow-up; require actual registration |
| Delegate a current-task subtask | Available native subagent spawn/message/wait tools | Does not create a user-owned sidebar task; requires a bounded authorized subtask |

`handoff_thread` moves another task and its Git state between checkout/worktree or hosts; it can interrupt running work. It is not the tool for sending an assignment to another session. Use it only for an explicitly requested environment move.

The currently exposed task tools have model/reasoning options but no Qoder-style `--yolo` permission switch. Do not invent permission fields or claim to have changed the target's mode; preserve its configured permissions and report unsupported mode requests.

## Existing task

1. Resolve the user-designated task through `list_threads`; do not guess from the latest title or overwrite an unrelated task. Read recent status and the existing assignment with `read_thread`.
2. Record its `threadId`, `hostId` when returned, and the latest known result/turn information as the dispatch baseline. For a Codex target, take a `wait_threads` snapshot with `timeoutMs: 0` before dispatch to obtain that wait tool's cursor. A `read_thread` pagination cursor is not a `wait_threads` cursor. Do not treat an already-idle task as completion of a new assignment.
3. Send the common dispatch brief with `send_message_to_thread`. Omit `model` and `thinking` to preserve current settings unless the user explicitly requested an override supported by this target.
4. Check the tool result and then wait for actual progress. If sending errors ambiguously, inspect the task for the assignment before retrying.

Do not assume that a message sent to a busy task is safely queued. For an unrelated running assignment, leave it untouched and resolve another authorized target. For a requested correction to the same assignment, send only the relevant update.

## Existing ChatGPT conversation

`list_threads`, `read_thread` and `send_message_to_thread` support chats as well as Codex tasks. Use the actual returned backing `kind` to choose the supervision path; a `kind: chatgpt` target is a ChatGPT conversation. This field does not prove its billing, quota bucket or remaining allowance. Do not promise separate or unlimited quota based on it.

1. Resolve the user-designated conversation and read its recent messages before dispatch. Record the latest visible message/result as the baseline, then send the brief once with `mcp__codex_app__send_message_to_thread`. Omit `model` and `thinking`: these overrides apply only to Codex tasks.
2. Do not call `wait_threads` for a ChatGPT conversation. While actively supervising, poll `read_thread` for a small number of recent turns at bounded intervals (normally 30–60 seconds); do not busy-poll or repeatedly load the full history. Compare with the dispatch baseline and inspect whether the new response actually answers this assignment.
3. Missing status or unchanged messages do not prove completion or failure. If reading fails, retry once after the polling interval; if it still fails, report monitoring unavailable and preserve the conversation identity for recovery. Follow the common deadline/blocker rules.
4. For requested after-turn monitoring, register the heartbeat below and explicitly save that this target uses `read_thread` polling, not `wait_threads`. Report completion only after inspecting the fresh answer and checking the requested deliverable.
5. Read or message the conversation without navigating the UI. Call `mcp__codex_app__navigate_to_codex_page` only when the user asks to open/show it. Do not assume a ChatGPT conversation has access to local repository files or can edit the supervisor's worktree; include the necessary authorized context and verify any claimed artifact separately.

Use the exact callable names exposed by the environment, such as `mcp__codex_app__list_threads` and `mcp__codex_app__read_thread`. The short `send_message_to_thread` in this document denotes the same MCP tool, not another tool; uppercase variants or names containing `AP_LIST_THREADS` are not aliases to invent.

## New independent task

Check which kind of task the creation tool actually supports. `target: {type: "chatgptWorkCloud"}` creates a ChatGPT Work cloud task only when explicitly requested; it is not a generic ordinary ChatGPT chat-creation switch. An existing `kind: chatgpt` conversation being readable/messageable does not imply that the current tool can create that kind. If ordinary chat creation is absent, say so and use an authorized available UI route or ask the user to create/select a conversation; never substitute a different product silently.

1. Confirm that the current request explicitly asks for a new task/session. Otherwise reuse a designated existing task or follow the subagent path; task-creation capability alone is not authorization.
2. For repository work, call `list_projects` and use its real `projectId`. Default to `environment: {type: "worktree"}` when `isGitRepository` is true and `local` otherwise. Follow an explicit request to use the saved project directly. Workspace OpenSpec/branch rules still apply inside the new task.
3. Set `startingState` only for a Git state the user explicitly requested. Do not invent a branch or assume a new worktree contains current uncommitted changes. For non-repository work use `projectless`; cloud work requires an explicit cloud request.
4. Pass the full dispatch brief as `prompt`. Omit model/reasoning overrides unless the user specified them; use live tool-supported values rather than a hard-coded model list. Never translate Qoder `performance`/`ultimate` levels into Codex model names.
5. Creation also dispatches the initial prompt and is non-blocking. A ready result supplies `threadId`/`hostId`; a queued setup may supply only `clientThreadId`. Do not pass `clientThreadId` to messaging/waiting tools that require `threadId`, and do not create a duplicate task because setup is pending.
6. Resolve the ready identity through the app's returned state/tools before further control. Use `list_threads` to locate a candidate and `read_thread` to confirm its initial assignment when needed; do not select a similarly named task without identity evidence. If it cannot yet be uniquely resolved, report setup-pending and continue permitted preparation or registered monitoring. Require actual cwd/branch confirmation before the worker edits code.
7. After a successful creation, include the app's required created-task directive in the final response: `::created-thread{threadId="..."}` for ready tasks or `::created-thread{clientThreadId="..."}` for queued setup, using the real returned value.

## Foreground supervision

For Codex targets, use `wait_threads` rather than repeatedly dumping `read_thread`. For ChatGPT conversations, use the bounded polling path above:

- Start with `timeoutMs: 0` for a compact snapshot when needed; use bounded waits up to 60,000 ms while actively supervising.
- Pass actual `threadId`, optional `hostId`, and the latest cursor returned by `wait_threads` as `afterCursor` for each target. A cursor avoids repeating already-delivered results; do not substitute a cursor from another tool.
- The call wakes on the first completion or attention event; it does not mean every target finished. Keep following remaining targets and inspect per-target `errors`.
- Commentary alone does not wake a wait. A timeout with unchanged progress is not a failure and not a reason to send the implementation prompt again.
- Use `read_thread` for the specific report, question or failure details required for the next decision. Verify actual files/state before declaring success.
- A freshly created task has no previous assignment. If its first snapshot already reports completion, verify that result rather than waiting for another state change.

`wait_threads` only waits while the call/turn is active. It does not register persistent wake-up or guarantee continuation after the supervisor ends the turn.

## Requested background monitoring

When the user asks to monitor, check back, notify on completion or continue after this turn, use the native scheduler if it is available:

1. Look for an existing matching automation using the current tool's documented discovery route; update it rather than create a duplicate. Use `automation_update` with `kind: heartbeat` attached to the current supervisor task. Do not substitute a standalone cron job unless the user explicitly requested one.
2. Save a cohesive prompt containing worker IDs/hosts, assignment identity and dispatch baseline, project/worktree and report location, acceptance checks, allowed follow-ups and stop conditions. Include an actual deadline when a timed window applies. Use real returned IDs; do not use titles as control identifiers.
3. Use a low-frequency cadence (normally five minutes, subject to the scheduler's supported settings). Honor the user's duration or explicit “until completion” request. If no stopping condition was given, use and disclose a bounded window, normally one hour; do not apply that default cutoff to an explicit completion-bound request. A deadline escalates monitoring status, not worker success, and does not kill the worker. Repeated blockers without new evidence follow the common escalation rule.
4. Instruct the heartbeat to stay quiet while progress is unchanged or non-actionable, and notify on meaningful changes, verified completion, failure or required user action. Keep mute/unmute preferences in `notificationPolicy`, not in the task prompt.
5. Require a successful registration result with the actual automation ID/state before promising after-turn follow-up. New-task creation may combine setup and dispatch; register/update monitoring once the actual worker identity is available, before ending the turn. Until then, foreground observation is the only confirmed supervision.
6. Each wake-up reads compact current state, verifies fresh evidence and applies the common completion/blocker rules. If a bounded corrective prompt is needed, keep monitoring tied to the same assignment and update its acceptance/baseline details; do not duplicate the worker or monitor.
7. After verified completion, a terminal blocker or the monitoring deadline, pause the task-specific heartbeat using `automation_update`; resolve its ID and preserve unrelated fields as required by the current schema. A pause is confirmed by the returned state, not merely by requesting it.

If scheduler tools are absent or registration fails, stay in foreground wait when supervision is still required, or explicitly report that no after-turn monitor is active. Desktop-local monitoring needs the app running, the computer awake and the project accessible; do not promise an always-on service.

See [official scheduled-task documentation](https://developers.openai.com/zh-Hans/docs/automations) for in-chat scheduling and local execution limits. Current native tool schemas own callable names, parameters and authorization requirements; documentation does not imply every Codex client exposes the same tools.
