#!/bin/sh
# Ensure the persistent data volume layout exists, seed the snippet database
# when missing, start the MCP server in the background (set ENABLE_MCP=0 to
# skip it), then run the given command (the web editor) in the foreground.
# SIGTERM/SIGINT stop both together.
set -eu

CV_DATA_ROOT="${CV_DATA_ROOT:-/data}"
export CV_DATA_ROOT
DB_PATH="${SNIPPETS_DB:-${CV_DATA_ROOT}/snippets.db}"
export SNIPPETS_DB="${DB_PATH}"
export RESUME_IMPORTS_DIR="${RESUME_IMPORTS_DIR:-${CV_DATA_ROOT}/imports}"

mkdir -p \
  "${CV_DATA_ROOT}/assets/images" \
  "${CV_DATA_ROOT}/imports/staging" \
  "${CV_DATA_ROOT}/cv/variants" \
  "${CV_DATA_ROOT}/cv/current" \
  "$(dirname "${DB_PATH}")"

if [ ! -f "$DB_PATH" ]; then
  echo "No snippet database at ${DB_PATH}; seeding from data.yaml and content/…"
  python3 -m cvbuilder.importer
fi

MCP_PID=""
if [ "${ENABLE_MCP:-1}" != "0" ]; then
  echo "Starting MCP server (${MCP_TRANSPORT:-stdio}) on ${MCP_HOST:-127.0.0.1}:${MCP_PORT:-8765}…"
  python3 scripts/mcp-server.py &
  MCP_PID=$!
fi

MAIN_PID=""
cleanup() {
  [ -n "$MCP_PID" ] && kill -TERM "$MCP_PID" 2>/dev/null || true
  [ -n "$MAIN_PID" ] && kill -TERM "$MAIN_PID" 2>/dev/null || true
}
trap cleanup TERM INT

"$@" &
MAIN_PID=$!
wait "$MAIN_PID"
STATUS=$?

cleanup
if [ -n "$MCP_PID" ]; then
  wait "$MCP_PID" 2>/dev/null || true
fi
exit "$STATUS"
