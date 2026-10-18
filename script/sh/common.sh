#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_DIR="$PROJECT_ROOT/logs"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

BACKEND_PORT="${POWER_TRADE_BACKEND_PORT:-8000}"
FRONTEND_PORT="${POWER_TRADE_FRONTEND_PORT:-5173}"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
CONTROL_LOCK_DIR="$RUN_DIR/control.lock"

PYTHON_BIN=""

info() {
  printf '  [INFO] %s\n' "$*"
}

ok() {
  printf '  [ OK ] %s\n' "$*"
}

warn() {
  printf '  [WARN] %s\n' "$*" >&2
}

die() {
  printf '  [FAIL] %s\n' "$*" >&2
  exit 1
}

ensure_runtime_dirs() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
}

acquire_control_lock() {
  local owner=""
  ensure_runtime_dirs
  if mkdir "$CONTROL_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$CONTROL_LOCK_DIR/owner.pid"
    return
  fi

  owner="$(sed -n '1p' "$CONTROL_LOCK_DIR/owner.pid" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; then
    die "另一条启停命令正在运行（PID ${owner}）；请等待其完成后重试。"
  fi

  rm -f "$CONTROL_LOCK_DIR/owner.pid"
  rmdir "$CONTROL_LOCK_DIR" 2>/dev/null || die "无法清理失效控制锁：$CONTROL_LOCK_DIR"
  mkdir "$CONTROL_LOCK_DIR" || die "无法创建控制锁：$CONTROL_LOCK_DIR"
  printf '%s\n' "$$" > "$CONTROL_LOCK_DIR/owner.pid"
}

release_control_lock() {
  local owner=""
  [ -d "$CONTROL_LOCK_DIR" ] || return
  owner="$(sed -n '1p' "$CONTROL_LOCK_DIR/owner.pid" 2>/dev/null | tr -d '[:space:]' || true)"
  if [ "$owner" = "$$" ]; then
    rm -f "$CONTROL_LOCK_DIR/owner.pid"
    rmdir "$CONTROL_LOCK_DIR" 2>/dev/null || true
  fi
}

write_pid_file() {
  local pid_file="$1" pid="$2" temporary
  temporary="$pid_file.tmp.$$"
  printf '%s\n' "$pid" > "$temporary"
  mv "$temporary" "$pid_file"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

os_name() {
  case "$(uname -s 2>/dev/null || true)" in
    Darwin) printf 'macos\n' ;;
    Linux) printf 'linux\n' ;;
    *) printf 'unknown\n' ;;
  esac
}

install_with_system_package_manager() {
  local description="$1"
  local brew_formula="$2"
  shift 2
  local apt_packages=("$@")

  case "$(os_name)" in
    macos)
      if command_exists brew; then
        info "正在通过 Homebrew 安装 $description ..."
        brew install "$brew_formula"
        return
      fi
      die "缺少 ${description}，且未检测到 Homebrew。请先安装 Homebrew（https://brew.sh/），再执行：brew install ${brew_formula}"
      ;;
    linux)
      if command_exists apt-get; then
        info "正在通过 apt 安装 $description ..."
        if [ "$(id -u)" -eq 0 ]; then
          apt-get update
          apt-get install -y "${apt_packages[@]}"
        elif command_exists sudo; then
          sudo apt-get update
          sudo apt-get install -y "${apt_packages[@]}"
        else
          die "缺少 ${description}。请以 root 执行：apt-get update && apt-get install -y ${apt_packages[*]}"
        fi
        return
      fi
      die "缺少 ${description}，当前 Linux 未检测到 apt。请使用系统包管理器安装：${apt_packages[*]}"
      ;;
    *)
      die "缺少 ${description}，且当前操作系统不支持自动安装。请先手动安装后重试。"
      ;;
  esac
}

select_python() {
  local candidate version
  for candidate in python3.12 python3.11; do
    if command_exists "$candidate"; then
      version="$($candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      case "$version" in
        3.11|3.12)
          PYTHON_BIN="$(command -v "$candidate")"
          export PYTHON_BIN
          return 0
          ;;
      esac
    fi
  done
  return 1
}

ensure_python() {
  if select_python; then
    return
  fi

  install_with_system_package_manager "Python 3.12" "python@3.12" python3 python3-venv
  select_python || die "已尝试安装 Python，但仍未找到 Python 3.11/3.12。macOS 可执行：brew install python@3.12；Ubuntu 可安装 python3.12 与 python3.12-venv。"
}

node_is_supported() {
  command_exists node || return 1
  node -e 'const [M,m]=process.versions.node.split(".").map(Number); process.exit((M>22 || (M===22 && m>=12)) ? 0 : 1)'
}

use_homebrew_node22() {
  local prefix
  command_exists brew || return 1
  prefix="$(brew --prefix node@22 2>/dev/null || true)"
  if [ -n "$prefix" ] && [ -x "$prefix/bin/node" ]; then
    PATH="$prefix/bin:$PATH"
    export PATH
  fi
  node_is_supported
}

ensure_node() {
  if node_is_supported; then
    return
  fi

  case "$(os_name)" in
    macos)
      command_exists brew || die "需要 Node.js 22.12+。请先安装 Homebrew（https://brew.sh/），再执行：brew install node@22"
      info "正在通过 Homebrew 安装 Node.js 22 ..."
      brew install node@22
      use_homebrew_node22 || die "Node.js 已安装但未进入 PATH。请执行：export PATH=\"$(brew --prefix node@22)/bin:\$PATH\""
      ;;
    linux)
      if ! command_exists node; then
        install_with_system_package_manager "Node.js 与 npm" "node@22" nodejs npm
      fi
      node_is_supported || die "需要 Node.js 22.12+，系统包管理器提供的版本不满足要求。请按 https://nodejs.org/ 的 Linux 安装说明安装 Node.js 22 LTS。"
      ;;
    *)
      die "需要 Node.js 22.12+。请从 https://nodejs.org/ 安装后重试。"
      ;;
  esac

  command_exists npm || die "Node.js 可用但缺少 npm；请安装带 npm 的 Node.js 22.12+ 发行版。"
}

ensure_curl() {
  command_exists curl && return
  install_with_system_package_manager "curl" "curl" curl
  command_exists curl || die "curl 安装失败。"
}

ensure_required_tools() {
  ensure_curl
  ensure_python
  ensure_node
  command_exists npm || die "缺少 npm；请安装带 npm 的 Node.js 22.12+。"
}

file_sha256() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

pid_is_alive() {
  local pid="$1" state
  kill -0 "$pid" 2>/dev/null || return 1
  state="$(ps -p "$pid" -o stat= 2>/dev/null | tr -d '[:space:]' || true)"
  [ -n "$state" ] && [ "${state#Z}" = "$state" ]
}

process_command() {
  ps -p "$1" -o command= 2>/dev/null || true
}

process_cwd() {
  local pid="$1"
  if [ -e "/proc/$pid/cwd" ]; then
    readlink "/proc/$pid/cwd" 2>/dev/null || true
    return
  fi
  if command_exists lsof; then
    lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | sed -n '1p'
  fi
}

process_matches_service() {
  local service="$1" pid="$2" command_line working_dir
  command_line="$(process_command "$pid")"
  working_dir="$(process_cwd "$pid")"
  case "$service" in
    backend)
      [ "$working_dir" = "$BACKEND_DIR" ] || return 1
      case "$command_line" in
        *"uvicorn app.main:app"*) return 0 ;;
      esac
      ;;
    frontend)
      [ "$working_dir" = "$FRONTEND_DIR" ] || return 1
      case "$command_line" in
        *"vite"*) return 0 ;;
      esac
      ;;
  esac
  return 1
}

read_pid_file() {
  local pid_file="$1" pid
  [ -f "$pid_file" ] || return 1
  pid="$(sed -n '1p' "$pid_file" | tr -d '[:space:]')"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 2
  printf '%s\n' "$pid"
}

port_listener_pid() {
  local port="$1"
  if command_exists lsof; then
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sed -n '1p'
    return
  fi
  if command_exists ss; then
    ss -ltnp "sport = :$port" 2>/dev/null \
      | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
      | sed -n '1p'
  fi
}

port_is_listening() {
  "$PYTHON_BIN" - "$1" <<'PY'
import socket
import sys

with socket.socket() as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

http_ok() {
  curl -fsS --max-time 3 "$1" >/dev/null 2>&1
}

json_health_ok() {
  local response
  response="$(curl -fsS --max-time 3 "$1" 2>/dev/null)" || return 1
  printf '%s' "$response" | "$PYTHON_BIN" -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("status") == "ok" else 1)' 2>/dev/null
}

docker_summary() {
  if ! command_exists docker; then
    printf '不需要；本机未安装 Docker'
  elif docker info >/dev/null 2>&1; then
    printf '不需要；Docker daemon 正在运行'
  else
    printf '不需要；已安装 Docker，但 daemon 未运行'
  fi
}
