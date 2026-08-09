#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

read -r -p "Feishu webhook URL: " webhook
read -r -p "Feishu signing secret (optional, press Enter to skip): " secret

if [ -z "$webhook" ]; then
  echo "webhook is required"
  exit 1
fi

touch .env
/Users/aibao/invest/.venv/bin/python - "$webhook" "$secret" <<'PY'
from pathlib import Path
import sys

path = Path(".env")
webhook, secret = sys.argv[1], sys.argv[2]
updates = {
    "FEISHU_WEBHOOK_URL": webhook,
    "FEISHU_BOT_SECRET": secret,
}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
seen = set()
output = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)
for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")
path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
PY

echo "saved Feishu bot config to .env"
