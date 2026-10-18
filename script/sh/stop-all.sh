#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

QUIET=false
SKIP_LOCK=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=true ;;
    --skip-lock) SKIP_LOCK=true ;;
    *) die "未知参数：$1" ;;
  esac
  shift
done

ensure_runtime_dirs
if [ "$SKIP_LOCK" = false ]; then
  acquire_control_lock
  trap release_control_lock EXIT
fi

say() {
  "$QUIET" || printf '%s\n' "$*"
}

stop_service() {
  local service="$1" label="$2" pid_file="$3" pid attempt

  if [ ! -f "$pid_file" ]; then
    say "  - ${label}：没有 PID 文件，已视为停止"
    return
  fi

  if ! pid="$(read_pid_file "$pid_file")"; then
    warn "$label 的 PID 文件无效；不会终止任何进程。"
    rm -f "$pid_file"
    return
  fi

  if ! pid_is_alive "$pid"; then
    rm -f "$pid_file"
    say "  - ${label}：PID ${pid} 已退出，已清理失效 PID 文件"
    return
  fi

  if ! process_matches_service "$service" "$pid"; then
    warn "$label 的 PID $pid 属于其他程序；拒绝终止，仅清理失效 PID 文件。"
    rm -f "$pid_file"
    return
  fi

  kill "$pid" 2>/dev/null || true
  attempt=0
  while pid_is_alive "$pid" && [ "$attempt" -lt 80 ]; do
    sleep 0.25
    attempt=$((attempt + 1))
  done

  if pid_is_alive "$pid"; then
    warn "${label} 未在 20 秒内退出，正在强制停止 PID ${pid}。"
    kill -KILL "$pid" 2>/dev/null || true
    attempt=0
    while pid_is_alive "$pid" && [ "$attempt" -lt 20 ]; do
      sleep 0.1
      attempt=$((attempt + 1))
    done
  fi

  if pid_is_alive "$pid"; then
    warn "$label PID $pid 仍存在，请人工检查：$(process_command "$pid")"
    return
  fi

  rm -f "$pid_file"
  say "  ✓ ${label} 已停止（PID ${pid}）"
}

say "停止 Power Trade Lab（只处理 .run/ 中记录且命令匹配的项目进程）..."
stop_service frontend "前端" "$FRONTEND_PID_FILE"
stop_service backend "后端" "$BACKEND_PID_FILE"
say "停止完成；数据库、日志和本地数据均已保留。"
