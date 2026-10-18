#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ensure_runtime_dirs
acquire_control_lock

started=false
cleanup_on_failure() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ] && [ "$started" = true ]; then
    warn "启动未完成，正在清理本次由项目脚本启动的进程。"
    "$SCRIPT_DIR/stop-all.sh" --quiet --skip-lock || true
  fi
  release_control_lock
  exit "$exit_code"
}
trap cleanup_on_failure EXIT

printf '启动 Power Trade Lab\n'
printf '项目目录：%s\n\n' "$PROJECT_ROOT"

info "检查运行环境（缺失时尝试使用系统包管理器安装）..."
ensure_required_tools
ok "$($PYTHON_BIN --version 2>&1)"
ok "Node.js $(node --version)，npm $(npm --version)"
info "Docker：$(docker_summary)（项目没有容器运行依赖）"

info "停止此前由本项目脚本管理的旧进程..."
"$SCRIPT_DIR/stop-all.sh" --quiet --skip-lock

if port_is_listening "$BACKEND_PORT"; then
  owner="$(port_listener_pid "$BACKEND_PORT" || true)"
  die "后端端口 ${BACKEND_PORT} 已被其他程序占用${owner:+（PID ${owner}）}；为避免误杀，启动已停止。"
fi
if port_is_listening "$FRONTEND_PORT"; then
  owner="$(port_listener_pid "$FRONTEND_PORT" || true)"
  die "前端端口 ${FRONTEND_PORT} 已被其他程序占用${owner:+（PID ${owner}）}；为避免误杀，启动已停止。"
fi

info "准备 Python 虚拟环境..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

venv_version="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$venv_version" in
  3.11|3.12) ;;
  *) die "${VENV_DIR} 使用 Python ${venv_version}；请将旧虚拟环境移出项目后重试。" ;;
esac

requirements_file="$BACKEND_DIR/requirements.txt"
requirements_marker="$VENV_DIR/.power-trade-requirements.sha256"
requirements_hash="$(file_sha256 "$requirements_file")"
installed_requirements_hash="$(sed -n '1p' "$requirements_marker" 2>/dev/null || true)"
if [ "$requirements_hash" != "$installed_requirements_hash" ] \
  || ! "$VENV_DIR/bin/python" -m pip check >/dev/null 2>&1 \
  || ! "$VENV_DIR/bin/python" -c 'import fastapi, sqlalchemy, uvicorn' >/dev/null 2>&1; then
  info "Python 依赖缺失或 requirements.txt 已变化，正在同步..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r "$requirements_file"
  "$VENV_DIR/bin/python" -m pip check
  printf '%s\n' "$requirements_hash" > "$requirements_marker"
else
  ok "Python 依赖未变化，复用现有虚拟环境"
fi

frontend_lock="$FRONTEND_DIR/package-lock.json"
frontend_marker="$FRONTEND_DIR/node_modules/.power-trade-lock.sha256"
frontend_hash="$(file_sha256 "$frontend_lock")"
installed_frontend_hash="$(sed -n '1p' "$frontend_marker" 2>/dev/null || true)"
if [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ] \
  || [ "$frontend_hash" != "$installed_frontend_hash" ] \
  || ! (cd "$FRONTEND_DIR" && npm ls --depth=0 >/dev/null 2>&1); then
  info "前端依赖缺失或 package-lock.json 已变化，正在执行 npm ci..."
  (cd "$FRONTEND_DIR" && PUPPETEER_SKIP_DOWNLOAD=true npm ci --no-audit --no-fund)
  printf '%s\n' "$frontend_hash" > "$frontend_marker"
else
  ok "前端依赖未变化，复用现有 node_modules"
fi

info "启动后端；应用生命周期将自动建表、执行幂等补列并补齐空表种子..."
(
  cd "$BACKEND_DIR"
  nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" </dev/null >"$BACKEND_LOG" 2>&1 &
  write_pid_file "$BACKEND_PID_FILE" "$!"
)
started=true
backend_pid="$(read_pid_file "$BACKEND_PID_FILE")"

backend_ready=false
for _attempt in $(seq 1 90); do
  if ! pid_is_alive "$backend_pid"; then
    break
  fi
  if json_health_ok "http://127.0.0.1:$BACKEND_PORT/api/health"; then
    backend_ready=true
    break
  fi
  sleep 1
done
if [ "$backend_ready" != true ]; then
  warn "后端未通过数据库健康检查。最近日志："
  tail -n 30 "$BACKEND_LOG" >&2 || true
  exit 1
fi
ok "后端已就绪（PID ${backend_pid}，端口 ${BACKEND_PORT}）"

info "启动前端 Vite 开发服务器..."
(
  cd "$FRONTEND_DIR"
  nohup ./node_modules/.bin/vite \
    --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort </dev/null >"$FRONTEND_LOG" 2>&1 &
  write_pid_file "$FRONTEND_PID_FILE" "$!"
)
frontend_pid="$(read_pid_file "$FRONTEND_PID_FILE")"

frontend_ready=false
for _attempt in $(seq 1 60); do
  if ! pid_is_alive "$frontend_pid"; then
    break
  fi
  if http_ok "http://127.0.0.1:$FRONTEND_PORT/"; then
    frontend_ready=true
    break
  fi
  sleep 1
done
if [ "$frontend_ready" != true ]; then
  warn "前端未通过 HTTP 检查。最近日志："
  tail -n 30 "$FRONTEND_LOG" >&2 || true
  exit 1
fi
ok "前端已就绪（PID ${frontend_pid}，端口 ${FRONTEND_PORT}）"

release_control_lock
trap - EXIT
printf '\n启动成功\n'
printf 'Web：       http://127.0.0.1:%s\n' "$FRONTEND_PORT"
printf '后端：      http://127.0.0.1:%s\n' "$BACKEND_PORT"
printf 'API 文档： http://127.0.0.1:%s/docs（仅开发模式）\n' "$BACKEND_PORT"
printf '日志：      %s\n' "$LOG_DIR"
printf '状态：      %s/status-all.sh\n' "$SCRIPT_DIR"
printf '停止：      %s/stop-all.sh\n' "$SCRIPT_DIR"
