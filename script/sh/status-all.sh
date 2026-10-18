#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ensure_runtime_dirs

if ! select_python; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi

printf 'Power Trade Lab 状态\n'
printf '项目目录：%s\n\n' "$PROJECT_ROOT"

overall_ok=true

service_status() {
  local service="$1" label="$2" pid_file="$3" port="$4" log_file="$5" health_kind="$6"
  local pid="" listener_pid="" state="未运行" detail=""

  if [ -f "$pid_file" ]; then
    if ! pid="$(read_pid_file "$pid_file")"; then
      state="异常"
      detail="PID 文件无效：$pid_file"
    elif ! pid_is_alive "$pid"; then
      state="异常"
      detail="PID $pid 已失效；可重复执行 stop-all.sh 清理"
    elif ! process_matches_service "$service" "$pid"; then
      state="异常"
      detail="PID $pid 当前属于其他程序，脚本不会终止它"
    else
      state="运行中"
    fi
  fi

  listener_pid="$(port_listener_pid "$port" || true)"
  if [ -n "$listener_pid" ]; then
    if [ -n "$pid" ] && [ "$listener_pid" != "$pid" ]; then
      state="异常"
      detail="端口 $port 由 PID $listener_pid 占用，与记录 PID ${pid:-无} 不一致"
    elif [ ! -f "$pid_file" ]; then
      state="异常"
      detail="端口 $port 被外部 PID $listener_pid 占用，项目没有对应 PID 文件"
    fi
  elif [ "$state" = "运行中" ]; then
    state="异常"
    detail="PID $pid 存活，但端口 $port 没有监听"
  fi

  if [ "$state" = "运行中" ]; then
    case "$health_kind" in
      backend)
        if [ -n "$PYTHON_BIN" ] && json_health_ok "http://127.0.0.1:$port/api/health"; then
          detail="数据库健康检查通过"
        else
          state="异常"
          detail="进程和端口存在，但 /api/health 未返回 status=ok"
        fi
        ;;
      frontend)
        if http_ok "http://127.0.0.1:$port/"; then
          detail="HTTP 入口可访问"
        else
          state="异常"
          detail="进程和端口存在，但首页不可访问"
        fi
        ;;
    esac
  fi

  printf '%-8s %-8s PID=%-8s 端口=%-5s %s\n' "$label" "$state" "${pid:--}" "$port" "$detail"
  printf '         日志：%s\n' "$log_file"
  [ "$state" = "运行中" ] || overall_ok=false
}

service_status backend "后端" "$BACKEND_PID_FILE" "$BACKEND_PORT" "$BACKEND_LOG" backend
service_status frontend "前端" "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "$FRONTEND_LOG" frontend

printf '\n基础设施\n'
printf 'Docker：%s\n' "$(docker_summary)"
printf '容器：无（仓库没有 Dockerfile 或 Compose 配置）\n'

if [ -f "$BACKEND_DIR/power_trade.db" ]; then
  if [ -r "$BACKEND_DIR/power_trade.db" ] && [ -w "$BACKEND_DIR/power_trade.db" ]; then
    printf 'SQLite：可读写（%s）\n' "$BACKEND_DIR/power_trade.db"
  else
    printf 'SQLite：异常，数据库文件不可读写（%s）\n' "$BACKEND_DIR/power_trade.db"
    overall_ok=false
  fi
else
  printf 'SQLite：尚未初始化；首次启动后自动创建（%s）\n' "$BACKEND_DIR/power_trade.db"
fi

printf '\n命令\n'
printf '启动：%s\n' "$SCRIPT_DIR/start-all.sh"
printf '停止：%s\n' "$SCRIPT_DIR/stop-all.sh"

if "$overall_ok"; then
  exit 0
fi
exit 1
