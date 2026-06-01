"""Notification: stdout always; Lark webhook if configured."""
from __future__ import annotations
import json
import urllib.request

from .config import LARK_WEBHOOK_URL, has_lark


def notify(title: str, body: str) -> None:
    print(f"\n=== {title} ===\n{body}\n")
    if has_lark():
        try:
            payload = json.dumps({
                "msg_type": "text",
                "content": {"text": f"{title}\n\n{body}"},
            }).encode("utf-8")
            req = urllib.request.Request(
                LARK_WEBHOOK_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as e:  # don't let notification failure break the pipeline
            print(f"[notify] Lark push failed: {e}")
