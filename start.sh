#!/usr/bin/env bash
# Power Trade Lab · 电力交易演练台 - 一键启动脚本
# 用法: ./start.sh
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
RUNTIME_DIR="$ROOT/.zcode/run"
LOG_DIR="$ROOT/.zcode/logs"
VENV_DIR="$ROOT/backend/.venv"
REQUIREMENTS_FILE="$ROOT/backend/requirements.txt"
REQUIREMENTS_MARKER="$VENV_DIR/.power-trade-requirements.sha256"
FRONTEND_LOCK="$ROOT/frontend/package-lock.json"
FRONTEND_MARKER="$ROOT/frontend/node_modules/.power-trade-lock.sha256"
mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
cd "$ROOT"

fail() {
  printf '   ✗ %s\n' "$1" >&2
  return 1
}

cleanup_on_failure() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    "$ROOT/stop.sh" --quiet >/dev/null 2>&1 || true
  fi
  return "$status"
}
trap cleanup_on_failure EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令：$1"
}

file_sha256() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

port_in_use() {
  "$PYTHON_BIN" -c 'import socket,sys; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); rc=s.connect_ex(("127.0.0.1",int(sys.argv[1]))); s.close(); raise SystemExit(0 if rc == 0 else 1)' "$1"
}

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
else
  fail "需要 Python 3.11 或 3.12。"
fi

require_command curl
require_command node
require_command npm

NODE_VERSION="$(node -p 'process.versions.node')"
NODE_SUPPORTED="$(node -p 'const [M,m]=process.versions.node.split(".").map(Number); Number((M===20&&m>=19)||(M===22&&m>=12)||M>22)')"
if [ "$NODE_SUPPORTED" != "1" ]; then
  fail "Node.js $NODE_VERSION 不受支持；需要 20.19+ 或 22.12+。"
fi

if [ -f "$RUNTIME_DIR/backend.pid" ] || [ -f "$RUNTIME_DIR/frontend.pid" ]; then
  "$ROOT/stop.sh" --quiet
fi

echo "⚡ Power Trade Lab · 电力交易演练台 启动中..."
echo "   Python: $($PYTHON_BIN --version 2>&1)"
echo "   Node:   v$NODE_VERSION"
echo ""

# ---------- 后端 ----------
echo "📦 [1/2] 准备并启动后端 (FastAPI :8000)..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "   首次运行，创建虚拟环境..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$VENV_VERSION" in
  3.11|3.12) ;;
  *) fail "$VENV_DIR 使用 Python $VENV_VERSION；请删除该目录后重新运行。" ;;
esac

REQUIREMENTS_HASH="$(file_sha256 "$REQUIREMENTS_FILE")"
INSTALLED_REQUIREMENTS_HASH="$(sed -n '1p' "$REQUIREMENTS_MARKER" 2>/dev/null || true)"
if [ "$REQUIREMENTS_HASH" != "$INSTALLED_REQUIREMENTS_HASH" ]; then
  echo "   同步 Python 依赖..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip -q
  "$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE" -q
  printf '%s\n' "$REQUIREMENTS_HASH" > "$REQUIREMENTS_MARKER"
fi

if port_in_use 8000; then
  fail "端口 8000 已被其他程序占用；为避免误杀，项目不会自动关闭它。"
fi

cd "$ROOT/backend"
"$VENV_DIR/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" > "$RUNTIME_DIR/backend.pid"
echo "   ✓ 后端已启动 (PID $BACKEND_PID)"

BACKEND_READY=false
for _attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && \
     curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    BACKEND_READY=true
    break
  fi
  sleep 1
done
if [ "$BACKEND_READY" != "true" ]; then
  echo "   ✗ 后端启动失败，最近日志："
  tail -20 "$LOG_DIR/backend.log" || true
  exit 1
fi
echo "   ✓ 后端就绪 http://127.0.0.1:8000"

# ---------- 前端 ----------
echo ""
echo "🖥️  [2/2] 准备并启动前端 (Vue 3 :5173)..."
FRONTEND_LOCK_HASH="$(file_sha256 "$FRONTEND_LOCK")"
INSTALLED_FRONTEND_HASH="$(sed -n '1p' "$FRONTEND_MARKER" 2>/dev/null || true)"
if [ ! -d "$ROOT/frontend/node_modules" ] || [ "$FRONTEND_LOCK_HASH" != "$INSTALLED_FRONTEND_HASH" ]; then
  echo "   按 package-lock.json 同步前端依赖..."
  cd "$ROOT/frontend"
  # Puppeteer 仅用于可选 E2E，不在基础启动时下载浏览器内核。
  PUPPETEER_SKIP_DOWNLOAD=true npm ci --no-audit --no-fund
  printf '%s\n' "$FRONTEND_LOCK_HASH" > "$FRONTEND_MARKER"
fi

if port_in_use 5173; then
  fail "端口 5173 已被其他程序占用；为避免误杀，项目不会自动关闭它。"
fi

cd "$ROOT/frontend"
./node_modules/.bin/vite --host 127.0.0.1 > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
printf '%s\n' "$FRONTEND_PID" > "$RUNTIME_DIR/frontend.pid"
echo "   ✓ 前端已启动 (PID $FRONTEND_PID)"

FRONTEND_READY=false
for _attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1; then
    FRONTEND_READY=true
    break
  fi
  sleep 1
done
if [ "$FRONTEND_READY" != "true" ]; then
  echo "   ✗ 前端启动失败，最近日志："
  tail -20 "$LOG_DIR/frontend.log" || true
  exit 1
fi

trap - EXIT
echo ""
echo "================================================"
echo "🎉 系统已启动！"
echo ""
echo "   📌 访问地址:  http://127.0.0.1:5173"
echo "   📌 API文档:   http://127.0.0.1:8000/docs"
echo ""
echo "   停止系统: ./stop.sh"
echo "================================================"
