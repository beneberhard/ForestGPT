#!/bin/sh
set -eu

API_PORT="${API_PORT:-8003}"
UI_PORT="${UI_PORT:-8501}"
PYTHON_BIN="${PYTHON_BIN:-python}"
export FORESTGPT_API_URL="http://127.0.0.1:${API_PORT}"

cleanup() {
  if [ -n "${API_PID:-}" ]; then
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

docker compose up -d
"$PYTHON_BIN" -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!

sleep 1
if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "FastAPI failed to start. Port ${API_PORT} may already be in use."
  exit 1
fi

echo "FastAPI: ${FORESTGPT_API_URL}/docs"
echo "Streamlit: http://127.0.0.1:${UI_PORT}"
"$PYTHON_BIN" -m streamlit run streamlit_app.py \
  --server.address 127.0.0.1 \
  --server.port "$UI_PORT"
