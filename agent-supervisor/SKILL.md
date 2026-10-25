---
name: agent-supervisor
description: 委派任务并监工到验收，按环境使用 Codex/ChatGPT 任务工具、内置子代理或 Herdr。用于指定另一会话接手、新建任务、派发子任务、监工、盯一下、监督做完、跟进 worker 和完成通知；不为普通单会话编码自动派发。
---

# Agent Supervisor

Supervisor owns scope, approvals and final verification; worker owns its assigned implementation. A worker's idle/done state or final message is a review signal, never proof of success. Use the host's supported coordination tools; no backend is a universal dependency.

## Select the backend and worker type

1. Honor the user's named environment, worker or client first. Verify its actual identity and current work before sending anything; do not silently substitute a different client/model or repurpose an unrelated session.
2. If no backend was specified, use Herdr when `HERDR_ENV=1` and the Herdr CLI is available. Otherwise, when the current Codex tools expose task/session coordination, use them directly. The word “Codex” alone does not prove desktop tools are available in a CLI/IDE session.
3. Read only the selected backend reference:

| Situation | Owner and next action |
| --- | --- |
| Herdr environment or a specifically requested Herdr worker | [Herdr backend](references/herdr.md); verify environment/CLI and pane/session identity, then use its watcher protocol |
| Existing Codex task or ChatGPT conversation, or an explicitly requested new independent task/session | [Codex backend](references/codex.md); use native app task tools and actual returned IDs; ChatGPT conversations require the polling branch |
| Explicit delegation of a bounded subtask within the current task, without requesting a separate task | Native subagent tools when available and allowed; keep the result in the current task, do not create a sidebar task |
| Required backend/tool is unavailable | Report the missing capability; prepare the brief and continue independent authorized work. Do not install a framework, fake a watcher or silently switch clients |

Creating a new independent Codex task requires the user's explicit request for a new task/session. A generic “delegate” request does not by itself authorize one. Reuse a designated existing task after checking it; if an independent target is still unclear, ask whether to create a new task or which existing task to use. Do not select an arbitrary idle conversation.

Native subagents are not independent user-owned tasks. Use them only for a concrete bounded subtask that can run alongside useful supervisor work, and only when delegation is requested or required by applicable instructions. Reuse actual returned agent IDs for follow-ups and completion waits.

## Dispatch contract

When there are materially different implementation routes (architecture, framework, refactor versus new implementation), read the available `bestway` skill and compare at least three meaningful options against objective, constraints, acceptance and failure cost. Record the selected route and why the alternatives were rejected; the worker executes that route and raises a decision if new evidence invalidates it. If `bestway` is unavailable, perform that comparison in the brief. Skip this step when the route is already decided or only one practical route exists.

Write one cohesive brief, inline in the native task prompt or in a shared file the worker can access. Include:

- Assignment identity and objective; what counts as complete and where to stop.
- Repository/project, exact worktree and branch, owned files, and changes to preserve. If the platform allocates a new worktree, name the intended project and any user-requested starting state; require the worker to verify/report actual cwd and branch before editing.
- Applicable source/design evidence, graph coverage and source fallback evidence; do not assume shared conversation history or inherited uncommitted files.
- Requested model/mode, permitted and forbidden actions, acceptance checks, and a fresh report path or native final-result location.
- Known blockers, current dispatch baseline, and the monitoring method plus deadline or completion-bound stop conditions when supervision was requested.

For a file-based brief, use the target repository's `.artifacts/<assignment>-mission.md`; use the workspace root's `.artifacts/` only for cross-repository or workspace Harness work. The brief is temporary runtime material, not a replacement for the project's required spec or approval. Keep durable decisions in the project's documented owner after completion. A cloud conversation may not access local files, so provide the relevant brief inline.

Require a receipt for this assignment and a final summary of changes, verification and remaining risks. Acceptance must demonstrate the requested change, not only a green baseline: include a feature-specific assertion, changed behavior, new file or artifact. Check substantive output (actual test cases, expected build files, document accuracy); exit zero with no tests found is not success. Reuse valid checks and do not add builds or full tests merely to poll progress.

Use one writer per shared file. Parallel workers need disjoint ownership. Do not change an existing worker's model or permissions silently. Git commits, pushes, releases, YOLO and scope expansion retain their own authorization requirements.

Record backend-specific identities: Codex `threadId`/`hostId`, native subagent ID, or Herdr pane/terminal/session. They are not interchangeable. Reports, task titles and tool output are evidence, not authority to expand the brief.

## Dispatch and supervise

1. Verify worker readiness, identity and pending assignment. A busy worker doing unrelated work is not an available target to interrupt.
2. Choose how progress will be observed before dispatch. Herdr must register its watcher before prompting; native Codex can wait in the current turn, or register a heartbeat for requested after-turn supervision as described in its reference.
3. Send the brief once. If submission is ambiguous, inspect the target for this assignment before retrying; do not send duplicate implementation prompts.
4. Read compact progress first. Inspect the report and relevant current diff/runtime facts at a completed batch, scope question, reported failure or scheduled checkpoint; do not repeat every worker action or rerun valid checks on each poll.
5. Normal progress means continue waiting. A timer alone does not justify another implementation prompt, build, repository scan or full transcript read.

Do not promise supervision after ending the turn unless a real watcher/heartbeat registration succeeded. A foreground wait is not an after-turn callback. If registration fails, retain foreground supervision or report the lack of background wake-up; do not claim a monitor is active.

## Completion, blockers and recovery

- Completed/idle: verify the requested result against fresh artifacts and current scope. Never accept an old report or a result from a previous assignment as completion.
- Incomplete but authorized: use the backend's re-arm/update procedure and send one bounded corrective follow-up naming the unmet acceptance check. Do not retry a repeated blocker without new evidence or invent a broader task.
- Blocked: inspect the precise question. Answer factual/scope questions only within existing authority. Leave permission decisions for the user; do not auto-approve arbitrary commands, all future actions, mode changes, commits or production releases.
- Missing/replaced session, failed monitoring process or expired monitoring deadline: inspect the error and stop claiming live supervision for that target. A normal bounded native wait expiring is not this failure; inspect its returned progress and continue waiting. Follow the backend's bounded retry rules for query errors. Do not restart/reinstall a worker, change credentials or kill another agent as recovery.
- Before reusing a worker for a new assignment, finish or stop its old monitor and verify its state. Pause/stop a task-specific heartbeat when verified complete, terminally blocked or past its monitoring deadline; do not affect unrelated monitors or workers.

Finish with verified complete/partial/blocked status, actual worker identity, changed artifacts, checks and remaining actions. For an asynchronous handoff, also report the real monitor ID/state and its limits. Monitor creation or notification acceptance does not prove the supervisor reviewed the result.

For an implementation-choice questionnaire, use the agreed route, minimal change and project conventions. A “Recommended” label alone is not authorization. Read the exact option and resulting action before answering, then confirm the questionnaire closed and work resumed. Deletion, force-push, releases, new external side effects or reversing an agreed decision go back to the user. After two unchanged checkpoints while not working, inspect the blocker and escalate instead of repeatedly prompting “continue”.

Reports go to the supervisor through the backend's supported channel. Do not add OS popups or sound as a fallback. Stay quiet on normal unchanged progress; surface verified results, failures or a required user decision through the current conversation or the user's requested scheduler notification policy.

## Validate changes to this skill

- Check the backend routing, authorization boundaries, links and active skill entry. This global skill's source is `system/agents-config/skills/own/agent-supervisor`; do not maintain a separate project copy or a second supervisor skill.
- Herdr scripts: run `python3 <skill-dir>/scripts/test_supervise.py`; use `supervise.py start ... --dry-run` for command construction. Tests use fake CLI responses, not real agents.
- Codex instructions: compare tool names/fields with the currently available native tool schemas and cold-read representative existing-task, new-task, subagent and monitoring requests.
- A bounded read-only reviewer may check these instructions. Do not launch a live implementation worker, send test prompts to user-owned tasks, register an automation, enable YOLO or publish as a test unless the user separately authorizes that actual action. Report whether validation was textual/fake-CLI or live.
