#!/bin/bash
# 只停止本项目通过 start.sh 记录的进程，绝不按端口误杀其他程序。
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT/.zcode/run"
QUIET="${1:-}"

[ "$QUIET" = "--quiet" ] || echo "🛑 停止 Power Trade Lab..."

stop_tracked_process() {
  name="$1"
  expected="$2"
  pid_file="$RUNTIME_DIR/$name.pid"

  if [ ! -f "$pid_file" ]; then
    [ "$QUIET" = "--quiet" ] || echo "   $name 未由本项目启动"
    return
  fi

  pid="$(sed -n '1p' "$pid_file")"
  if ! printf '%s' "$pid" | grep -Eq '^[0-9]+$'; then
    echo "   ⚠ $name PID 文件无效，已忽略"
    rm -f "$pid_file"
    return
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    [ "$QUIET" = "--quiet" ] || echo "   $name 已停止"
    return
  fi

  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  case "$command_line" in
    *"$expected"*) ;;
    *)
      echo "   ⚠ PID $pid 已不属于本项目的 $name，拒绝终止"
      rm -f "$pid_file"
      return
      ;;
  esac

  kill "$pid" 2>/dev/null || true
  attempts=0
  while kill -0 "$pid" 2>/dev/null && [ "$attempts" -lt 20 ]; do
    sleep 0.25
    attempts=$((attempts + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "   ⚠ $name 未正常退出，执行强制终止"
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  [ "$QUIET" = "--quiet" ] || echo "   ✓ $name 已停止"
}

stop_tracked_process "backend" "uvicorn app.main:app"
stop_tracked_process "frontend" "vite --host 127.0.0.1"

[ "$QUIET" = "--quiet" ] || echo "完成。"
