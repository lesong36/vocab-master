#!/bin/bash
# 双击此文件：启动本地服务并打开背单词页面（macOS）

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=8080
URL="http://127.0.0.1:${PORT}/vocabulary_app.html"
LOG="$DIR/vocab_server.log"
PIDFILE="$DIR/.vocab_server.pid"

health_ok() {
  curl -s --max-time 2 "http://127.0.0.1:${PORT}/api/health" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'
}

port_in_use() {
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

port_owner_pids() {
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -t 2>/dev/null | sort -u
}

stop_stale_server() {
  local pids killed=0
  pids="$(port_owner_pids)"
  if [ -z "$pids" ]; then
    return 1
  fi
  for pid in $pids; do
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if echo "$cmd" | grep -q "vocab_server.py"; then
      kill "$pid" 2>/dev/null && killed=1
    fi
  done
  if [ "$killed" -eq 1 ]; then
    sleep 0.5
  fi
  [ "$killed" -eq 1 ]
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "启动失败：未找到 python3，请先安装 Python 3。"
  echo "日志: $LOG"
  sleep 3
  exit 1
fi

if health_ok; then
  open "$URL"
  echo "服务已在运行，已打开浏览器。"
  sleep 2
  exit 0
fi

if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    if health_ok; then
      open "$URL"
      echo "服务已在运行 (PID $OLD_PID)，已打开浏览器。"
      sleep 2
      exit 0
    fi
    kill "$OLD_PID" 2>/dev/null
    sleep 0.5
  fi
  rm -f "$PIDFILE"
fi

if port_in_use; then
  echo "端口 ${PORT} 已被占用，正在清理旧服务..."
  stop_stale_server || true
  if port_in_use; then
    echo "启动失败：端口 ${PORT} 仍被其他程序占用。"
    echo "可执行: lsof -i :${PORT}"
    echo "日志: $LOG"
    sleep 3
    exit 1
  fi
fi

nohup python3 "$DIR/vocab_server.py" "$PORT" >> "$LOG" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PIDFILE"

for _ in 1 2 3 4 5; do
  sleep 1
  if health_ok; then
    open "$URL"
    echo "VocabMaster 已启动 (PID $SERVER_PID)"
    echo "页面: $URL"
    echo "数据: $DIR/vocab_data.json"
    echo "可关闭此窗口，服务会在后台继续运行。"
    sleep 3
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
done

echo "启动失败，请查看日志末尾错误信息。"
echo "日志: $LOG"
tail -n 8 "$LOG" 2>/dev/null
sleep 3
exit 1
