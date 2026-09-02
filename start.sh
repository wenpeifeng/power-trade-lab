#!/bin/bash
# Power Trade Lab · 电力交易演练台 - 一键启动脚本
# 用法: ./start.sh
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT/.zcode/run"
LOG_DIR="$ROOT/.zcode/logs"
VENV_DIR="$ROOT/backend/.venv"
mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
cd "$ROOT"

port_in_use() {
  python3 -c 'import socket,sys; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); rc=s.connect_ex(("127.0.0.1",int(sys.argv[1]))); s.close(); raise SystemExit(0 if rc == 0 else 1)' "$1"
}

if [ -f "$RUNTIME_DIR/backend.pid" ] || [ -f "$RUNTIME_DIR/frontend.pid" ]; then
  "$ROOT/stop.sh" --quiet
fi

echo "⚡ Power Trade Lab · 电力交易演练台 启动中..."
echo ""

# ---------- 后端 ----------
echo "📦 [1/2] 启动后端 (FastAPI :8000)..."
cd "$ROOT/backend"
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
else
  echo "   ✗ 需要 Python 3.11 或 3.12；Python 3.10 以下已结束或接近结束安全维护。"
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "   首次运行，创建虚拟环境..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip -q
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt -q
fi

VENV_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$VENV_VERSION" in
  3.11|3.12) ;;
  *)
    echo "   ✗ $VENV_DIR 使用 Python $VENV_VERSION；请重建为 Python 3.11/3.12。"
    exit 1
    ;;
esac

if port_in_use 8000; then
  echo "   ✗ 端口 8000 已被其他程序占用；为避免误杀，项目不会自动关闭它。"
  exit 1
fi

# 通过 Python 模块启动，避免虚拟环境移动后 uvicorn 脚本仍引用旧绝对路径。
"$VENV_DIR/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" > "$RUNTIME_DIR/backend.pid"
echo "   ✓ 后端已启动 (PID $BACKEND_PID)"

# 等后端就绪
BACKEND_READY=false
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "   ✓ 后端就绪 http://127.0.0.1:8000"
    BACKEND_READY=true
    break
  fi
  sleep 1
done
if [ "$BACKEND_READY" != "true" ]; then
  echo "   ✗ 后端启动失败，最近日志："
  tail -20 "$LOG_DIR/backend.log"
  "$ROOT/stop.sh" --quiet
  exit 1
fi

# ---------- 前端 ----------
echo ""
echo "🖥️  [2/2] 启动前端 (Vue3 :5173)..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "   首次运行，安装依赖..."
  npm install
  npm install vue-router@4 element-plus @element-plus/icons-vue echarts axios driver.js
fi

if port_in_use 5173; then
  echo "   ✗ 端口 5173 已被其他程序占用；为避免误杀，项目不会自动关闭它。"
  "$ROOT/stop.sh" --quiet
  exit 1
fi

./node_modules/.bin/vite --host 127.0.0.1 > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
printf '%s\n' "$FRONTEND_PID" > "$RUNTIME_DIR/frontend.pid"
echo "   ✓ 前端已启动 (PID $FRONTEND_PID)"

FRONTEND_READY=false
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:5173/ >/dev/null 2>&1; then
    FRONTEND_READY=true
    break
  fi
  sleep 1
done
if [ "$FRONTEND_READY" != "true" ]; then
  echo "   ✗ 前端启动失败，最近日志："
  tail -20 "$LOG_DIR/frontend.log"
  "$ROOT/stop.sh" --quiet
  exit 1
fi
echo ""
echo "================================================"
echo "🎉 系统已启动！"
echo ""
echo "   📌 访问地址:  http://127.0.0.1:5173"
echo "   📌 API文档:   http://127.0.0.1:8000/docs"
echo ""
echo "   停止系统: ./stop.sh"
echo "================================================"
