#!/usr/bin/env bash
# supervisor-watch.sh — Herdr 监工看门狗（harness 无关：pi/codex/claude 通用）
#
# 用法: supervisor-watch.sh [CONF_DIR]
#   CONF_DIR 优先级：命令行参数 > $SUPERVISOR_WATCH_CONF > 当前工作目录的
#   data/supervisor-watch（随仓忽略，不占 home）。
#   每个 *.conf 监督一个 agent。
#
# conf 文件格式（KEY=VALUE 行，值可含空格、无需引号）:
#   AGENT=ev-web             # herdr agent 名（必填）
#   LOG=/path/monitor.log    # 监控日志路径（必填）
#   TITLE=ev-web             # 通知标题前缀（可选，默认用 AGENT）
#   CHECK_CMD=...            # 完成标准检查命令，exit 0 判定完成（可选）
#   WORK_DIR=...             # CHECK_CMD 执行目录（可选，默认当前目录）
#   IDLE_STUCK_ROUNDS=3      # 连续多少轮 idle 且未完成算"疑似卡住"（可选）
#
# 状态机（每轮每 agent）:
#   working       -> 清零计数
#   blocked       -> 通知一次"需要你决定"
#   idle/done     -> CHECK_CMD exit 0 -> 通知一次"任务完成"
#                    否则累计 idle 轮数，超阈值通知一次"疑似卡住"
#   herdr 不可用  -> 只记日志不通知
#
# 状态文件存在 CONF_DIR/.state/<AGENT>.state，删掉即重置计数与通知去重。

set -u
default_conf="$PWD/data/supervisor-watch"
CONF_DIR="${1:-${SUPERVISOR_WATCH_CONF:-$default_conf}}"
STATE_DIR="$CONF_DIR/.state"
mkdir -p "$STATE_DIR"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

val() { # conf key -> 值（取最后一行，允许值含空格/引号）
  sed -n "s/^$2=//p" "$1" | tail -1
}

get_status() {
  herdr agent get "$1" 2>/dev/null | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["result"]["agent"]["agent_status"])
except Exception:
    print("unknown")'
}

notify() {
  # 通知对象是 agent 不是人类：只走 herdr 通知（尽力而为），禁止 OS 弹窗/声音。
  # 主报告通道是 worker 通过 intercom 直接发给主会话（见 supervisor 技能）；
  # 看门狗只是 deadman，通知失败不影响判定，全部写日志。
  local result shown
  result="$(herdr notification show "$1" --body "$2" 2>/dev/null)"
  shown="$(printf '%s' "$result" | python3 -c 'import json,sys
try:
    print(str(json.load(sys.stdin)["result"].get("shown", False)).lower())
except Exception:
    print("false")' 2>/dev/null)"
  [ "$shown" = "true" ]
}

log() { # LOG message...
  local logf="$1"
  shift
  echo "[$(ts)] $*" >>"$logf"
}

shopt -s nullglob
for conf in "$CONF_DIR"/*.conf; do
  AGENT="$(val "$conf" AGENT)"
  [ -n "$AGENT" ] || continue
  LOG="$(val "$conf" LOG)"
  [ -n "$LOG" ] || LOG="$CONF_DIR/$AGENT-monitor.log"
  TITLE="$(val "$conf" TITLE)"
  [ -n "$TITLE" ] || TITLE="$AGENT"
  CHECK_CMD="$(val "$conf" CHECK_CMD)"
  WORK_DIR="$(val "$conf" WORK_DIR)"
  IDLE_STUCK_ROUNDS="$(val "$conf" IDLE_STUCK_ROUNDS)"
  [ -n "$IDLE_STUCK_ROUNDS" ] || IDLE_STUCK_ROUNDS=3

  state="$STATE_DIR/$AGENT.state"
  idle_rounds=0
  last_notified=""
  done_flag=0
  # shellcheck disable=SC1090
  [ -f "$state" ] && source "$state"

  status="$(get_status "$AGENT")"
  action="none"

  case "$status" in
  working)
    idle_rounds=0
    last_notified=""
    ;;
  blocked)
    if [ "$last_notified" != "blocked" ]; then
      notify "$TITLE: 需要你决定" "agent 处于 blocked 状态，可能弹出问卷或等待批准，请查看 pane" ||
        log "$LOG" "status=blocked idle=$idle_rounds action=notify-failed detail=通知渠道全部失败，直接看 pane"
      last_notified="blocked"
      action="escalated"
    fi
    ;;
  idle | done)
    completed=1
    if [ -n "$CHECK_CMD" ]; then
      if [ -n "$WORK_DIR" ] && [ ! -d "$WORK_DIR" ]; then
        log "$LOG" "status=$status idle=$idle_rounds action=error detail=WORK_DIR 不存在: $WORK_DIR"
        continue
      fi
      if (cd "${WORK_DIR:-.}" && bash -c "$CHECK_CMD") >/dev/null 2>&1; then
        completed=0
      fi
    fi
    if [ "$done_flag" != "1" ] && [ "$completed" = "0" ]; then
      notify "$TITLE: 任务完成" "完成标准检查通过（CHECK_CMD exit 0），请主会话核验交账" ||
        log "$LOG" "status=$status idle=$idle_rounds action=notify-failed detail=完成通知发送失败，直接看 pane"
      done_flag=1
      action="done"
    elif [ "$done_flag" != "1" ]; then
      idle_rounds=$((idle_rounds + 1))
      if [ "$idle_rounds" -ge "$IDLE_STUCK_ROUNDS" ] && [ "$last_notified" != "stuck" ]; then
        notify "$TITLE: 疑似卡住" "连续 $idle_rounds 轮 idle 且完成标准未满足，请检查 pane 或催进度" ||
          log "$LOG" "status=$status idle=$idle_rounds action=notify-failed detail=卡住通知发送失败，直接看 pane"
        last_notified="stuck"
        action="escalated"
      fi
    fi
    ;;
  *)
    # herdr server 没开 / agent 已释放：只记录
    log "$LOG" "status=$status idle=$idle_rounds action=none detail=agent 不可达或已退出"
    {
      echo "idle_rounds=$idle_rounds"
      echo "last_notified=\"$last_notified\""
      echo "done_flag=$done_flag"
    } >"$state"
    continue
    ;;
  esac

  log "$LOG" "status=$status idle=$idle_rounds action=$action detail=watchdog"
  {
    echo "idle_rounds=$idle_rounds"
    echo "last_notified=\"$last_notified\""
    echo "done_flag=$done_flag"
  } >"$state"
done
