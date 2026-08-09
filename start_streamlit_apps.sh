#!/bin/zsh
set -euo pipefail

WORKSPACE="/Users/aibao/invest"
STREAMLIT="$WORKSPACE/.venv/bin/streamlit"

if ! lsof -nP -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$WORKSPACE/pit-radar"
    DATABASE_URL="sqlite+pysqlite:///data/demo/pit_radar.sqlite" \
      nohup "$STREAMLIT" run src/pit_radar/ui/app.py \
      --server.address 127.0.0.1 --server.port 8501 \
      > logs/streamlit_pit_radar.out 2>&1 &
  )
fi

if ! lsof -nP -iTCP:8502 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$WORKSPACE/options"
    nohup "$STREAMLIT" run app.py \
      --server.address 127.0.0.1 --server.port 8502 \
      > streamlit_options.out 2>&1 &
  )
fi

if ! lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$WORKSPACE/trading-app"
    nohup "$WORKSPACE/trading-app/node_modules/.bin/next" dev \
      --hostname 127.0.0.1 --port 3000 \
      > trading_app.out 2>&1 &
  )
fi

open http://127.0.0.1:8501
open http://127.0.0.1:8502
open http://127.0.0.1:3000
