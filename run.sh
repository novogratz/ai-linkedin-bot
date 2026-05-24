#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$TIMESTAMP] Starting Neolegal LinkedIn Bot..." | tee -a "$LOG_DIR/run.log"

.venv/bin/python main.py >> "$LOG_DIR/run.log" 2>&1

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$TIMESTAMP] Neolegal LinkedIn Bot stopped (exit code: $?)" | tee -a "$LOG_DIR/run.log"
