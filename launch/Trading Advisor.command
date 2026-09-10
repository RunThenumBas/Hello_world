#!/bin/bash
# Double-click launcher (macOS): starts the local dashboard server and opens
# it in your browser. Safe to leave this Terminal window open while you work;
# closing it (or Ctrl+C) stops the server. Re-running just re-opens your
# browser if the server's already up.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$REPO_DIR/.venv"
PORT="${TRADING_ADVISOR_PORT:-8787}"
URL="http://127.0.0.1:$PORT/"

cd "$REPO_DIR"

echo "Thematic Trade Signals"
echo "======================"

if [ ! -d "$VENV_DIR" ]; then
  echo "First run: setting up a virtual environment (this takes a minute)..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet --upgrade pip
  "$VENV_DIR/bin/pip" install --quiet -r requirements.txt
fi

# Already running? Just open the browser.
if curl -sS -o /dev/null -m 1 "$URL" 2>/dev/null; then
  echo "Already running at $URL -- opening your browser."
  open "$URL"
  exit 0
fi

if [ -f "$REPO_DIR/.env" ]; then
  echo "Using ANTHROPIC_API_KEY from .env for long-term-hold research."
else
  echo "No .env with ANTHROPIC_API_KEY found -- long-term-hold research will be"
  echo "skipped (technical signals still refresh normally). See README.md to add one."
fi

echo "Starting server at $URL ..."
"$VENV_DIR/bin/python" -m trading_advisor.server --port "$PORT" --no-browser &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

for _ in $(seq 1 30); do
  if curl -sS -o /dev/null -m 1 "$URL" 2>/dev/null; then
    open "$URL"
    break
  fi
  sleep 0.5
done

echo "Server running. Close this window (or press Ctrl+C) to stop it."
wait "$SERVER_PID"
