#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
echo "═══════════════════════════════════════════════════" | tee -a "$LOG_DIR/run.log"
echo "  🚀 Neolegal LinkedIn Bot — $TIMESTAMP" | tee -a "$LOG_DIR/run.log"
echo "═══════════════════════════════════════════════════" | tee -a "$LOG_DIR/run.log"

.venv/bin/python main.py 2>&1 | tee -a "$LOG_DIR/run.log"

EXIT_CODE=${PIPESTATUS[0]}
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
echo "───────────────────────────────────────────────────" | tee -a "$LOG_DIR/run.log"
echo "  🛑 Bot stopped at $TIMESTAMP (exit: $EXIT_CODE)" | tee -a "$LOG_DIR/run.log"
echo "" >> "$LOG_DIR/run.log"
