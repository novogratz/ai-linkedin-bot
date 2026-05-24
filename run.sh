#!/bin/bash
set -e
cd "$(dirname "$0")"
LOG_DIR="logs"
PID_FILE="$LOG_DIR/scheduler.pid"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Kill existing scheduler if running
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[$TIMESTAMP] Stopping existing scheduler (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null
    sleep 1
  fi
fi

echo "═══════════════════════════════════════════════════" | tee -a "$LOG_DIR/run.log"
echo "  Neolegal LinkedIn Bot — $TIMESTAMP" | tee -a "$LOG_DIR/run.log"
echo "═══════════════════════════════════════════════════" | tee -a "$LOG_DIR/run.log"

nohup .venv/bin/python main.py >> "$LOG_DIR/run.log" 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > "$PID_FILE"

echo "  Scheduler started (PID $BOT_PID) in background" | tee -a "$LOG_DIR/run.log"
echo "  To stop: kill $BOT_PID" | tee -a "$LOG_DIR/run.log"
echo "  Logs: $LOG_DIR/run.log" | tee -a "$LOG_DIR/run.log"
