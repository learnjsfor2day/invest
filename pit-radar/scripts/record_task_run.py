#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_HISTORY_FILE = Path("logs/task_runs.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Append one scheduled task run record to a JSONL history file.")
    parser.add_argument("--task", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--exit-code", required=True)
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE))
    args = parser.parse_args()

    status_path = Path(args.status_file)
    log_path = Path(args.log_file)
    status = parse_status_file(status_path)
    exit_code = int_or_text(args.exit_code)
    started_at = status.get("started_at", "")
    finished_at = status.get("finished_at", "")
    record = {
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        "task": args.task,
        "label": args.label,
        "status": "success" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds(started_at, finished_at),
        "status_file": normalized_path(status_path),
        "log_file": normalized_path(log_path),
        "summary": tail_summary(log_path),
        "details": safe_details(status),
    }
    history_path = Path(args.history_file)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if run_record_exists(history_path, record):
        print("task_run_duplicate=true skipped append", flush=True)
        return
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_status_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    output: dict[str, str] = {}
    for line in text.splitlines():
        for part in line.strip().split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            output[key] = value
    return output


def safe_details(status: dict[str, str]) -> dict[str, str]:
    blocked = {"pid", "log", "started_at", "finished_at", "exit_code"}
    return {key: value for key, value in status.items() if key not in blocked and "key" not in key.lower()}


def run_record_exists(path: Path, record: dict[str, object]) -> bool:
    if not path.exists():
        return False
    record_key = task_run_key(record)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for line in lines:
        if not line.strip():
            continue
        try:
            existing = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(existing, dict) and task_run_key(existing) == record_key:
            return True
    return False


def task_run_key(record: dict[str, object]) -> tuple[object, object, object, object, object]:
    return (
        record.get("label"),
        record.get("started_at"),
        record.get("finished_at"),
        record.get("log_file"),
        record.get("exit_code"),
    )


def tail_summary(path: Path, max_lines: int = 8) -> str:
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except Exception:
        return ""
    interesting = [line for line in lines if any(token in line.lower() for token in ["error", "traceback", "failed", "exit_code", "summary", "final_missing"])]
    selected = interesting[-max_lines:] if interesting else lines[-max_lines:]
    return "\n".join(selected)


def duration_seconds(started_at: str, finished_at: str) -> int | None:
    start = parse_datetime(started_at)
    finish = parse_datetime(finished_at)
    if start is None or finish is None:
        return None
    return max(0, int((finish - start).total_seconds()))


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def int_or_text(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def normalized_path(path: Path) -> str:
    return str(path)


if __name__ == "__main__":
    main()
