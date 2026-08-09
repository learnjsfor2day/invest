#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import desc, func, select

from pit_radar.db.models import MacroEventSnapshot
from pit_radar.db.session import create_session_factory
from pit_radar.time import ensure_utc, utc_now


DEFAULT_STATE_FILE = Path("logs/macro_event_reminders.json")
CN_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Feishu reminders for upcoming high-impact macro events from the PIT database.")
    parser.add_argument("--lookahead-days", type=int, default=3)
    parser.add_argument("--countries", default="US")
    parser.add_argument("--impact-levels", default="High")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--webhook-url", default="")
    parser.add_argument("--secret", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ignore-state", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    now = utc_now()
    countries = parse_csv(args.countries)
    impact_levels = parse_csv(args.impact_levels)
    events = upcoming_latest_macro_events(now, args.lookahead_days, countries, impact_levels)
    state_file = Path(args.state_file)
    state = {} if args.ignore_state else read_state(state_file)
    pending = [event for event in events if reminder_key(event) not in state]

    print(
        f"lookahead_days={args.lookahead_days} countries={','.join(countries)} "
        f"impact_levels={','.join(impact_levels)} events={len(events)} pending={len(pending)}",
        flush=True,
    )
    if not pending:
        return

    text = build_message(pending, now)
    print(text, flush=True)
    if args.dry_run:
        return

    webhook_url = args.webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
    secret = args.secret or os.getenv("FEISHU_BOT_SECRET", "")
    if not webhook_url:
        print("FEISHU_WEBHOOK_URL is not configured; reminder was not sent.", flush=True)
        return
    send_feishu_text(webhook_url, text, secret=secret)
    for event in pending:
        state[reminder_key(event)] = {
            "sent_at": now.isoformat(),
            "event_name": event.event_name,
            "release_at_utc": ensure_utc(event.release_at_utc).isoformat() if event.release_at_utc else "",
            "impact": event.impact or "",
        }
    write_state(state_file, state)


def upcoming_latest_macro_events(
    now: datetime,
    lookahead_days: int,
    countries: list[str],
    impact_levels: list[str],
) -> list[MacroEventSnapshot]:
    start = ensure_utc(now)
    end = start + timedelta(days=max(0, lookahead_days))
    latest = (
        select(
            MacroEventSnapshot.id.label("event_id"),
            func.row_number()
            .over(
                partition_by=MacroEventSnapshot.event_key,
                order_by=(desc(MacroEventSnapshot.observed_at_utc), desc(MacroEventSnapshot.id)),
            )
            .label("rank"),
        )
        .subquery()
    )
    stmt = (
        select(MacroEventSnapshot)
        .join(latest, MacroEventSnapshot.id == latest.c.event_id)
        .where(
            latest.c.rank == 1,
            MacroEventSnapshot.release_at_utc >= start,
            MacroEventSnapshot.release_at_utc <= end,
        )
        .order_by(MacroEventSnapshot.release_at_utc, MacroEventSnapshot.event_name)
    )
    if countries:
        stmt = stmt.where(MacroEventSnapshot.country.in_(countries))
    if impact_levels:
        stmt = stmt.where(MacroEventSnapshot.impact.in_(impact_levels))
    session_factory = create_session_factory()
    with session_factory() as session:
        return list(session.scalars(stmt).all())


def build_message(events: list[MacroEventSnapshot], now: datetime) -> str:
    lines = [
        "【PIT Radar 宏观事件提醒】",
        f"生成时间：{format_time(now)}",
        f"未来窗口：{len(events)} 个高影响事件",
        "",
    ]
    for event in events:
        release_at = ensure_utc(event.release_at_utc) if event.release_at_utc else None
        lines.append(f"- {event.event_name} ({event.country or 'N/A'}, {event.impact or 'N/A'})")
        if release_at:
            lines.append(f"  公布时间：{format_time(release_at)} / {format_time(release_at, NY_TZ)}")
        lines.append(f"  预期：{event.estimate_raw or '暂无'}；前值：{event.previous_raw or '暂无'}；实际：{event.actual_raw or '未公布'}")
    return "\n".join(lines)


def send_feishu_text(webhook_url: str, text: str, secret: str = "") -> None:
    payload: dict[str, object] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = feishu_sign(timestamp, secret)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "pit-radar/0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status >= 300:
                raise RuntimeError(f"Feishu webhook failed: {response.status} {body[:300]}")
            print(f"feishu_sent status={response.status} body={body[:300]}", flush=True)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu webhook failed: {exc.code} {body[:300]}") from exc


def feishu_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def reminder_key(event: MacroEventSnapshot) -> str:
    release = ensure_utc(event.release_at_utc).isoformat() if event.release_at_utc else ""
    return f"{event.event_key}|{release}|{event.impact or ''}"


def read_state(path: Path) -> dict[str, dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def write_state(path: Path, state: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_time(value: datetime, tz=CN_TZ) -> str:
    localized = ensure_utc(value).astimezone(tz)
    label = "北京时间" if tz == CN_TZ else "纽约时间"
    return f"{localized:%Y-%m-%d %H:%M} {label}"


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
