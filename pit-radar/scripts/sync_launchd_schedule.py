#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = PROJECT_ROOT / "config" / "task_schedule.json"
LAUNCHD_DIR = PROJECT_ROOT / "launchd"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


@dataclass(frozen=True)
class TaskDefinition:
    label: str
    script: str
    stdout_name: str
    stderr_name: str
    default_times: tuple[str, ...]
    default_days: tuple[int, ...] = ()


TASK_DEFINITIONS = (
    TaskDefinition("com.aibao.pitradar.daily", "scripts/run_daily_fmp_once.sh", "launchd_pitradar_daily.out", "launchd_pitradar_daily.err", ("07:30",)),
    TaskDefinition(
        "com.aibao.pitradar.estimates",
        "scripts/run_estimates_snapshot_once.sh",
        "launchd_pitradar_estimates.out",
        "launchd_pitradar_estimates.err",
        ("09:20",),
    ),
    TaskDefinition(
        "com.aibao.pitradar.earnings",
        "scripts/run_earnings_events_once.sh",
        "launchd_pitradar_earnings.out",
        "launchd_pitradar_earnings.err",
        ("08:10", "22:10"),
    ),
    TaskDefinition(
        "com.aibao.pitradar.macro",
        "scripts/run_macro_calendar_once.sh",
        "launchd_pitradar_macro.out",
        "launchd_pitradar_macro.err",
        ("07:05", "20:40", "22:10"),
    ),
    TaskDefinition(
        "com.aibao.pitradar.macro-reminder",
        "scripts/run_macro_reminder_once.sh",
        "launchd_pitradar_macro_reminder.out",
        "launchd_pitradar_macro_reminder.err",
        ("07:20",),
    ),
    TaskDefinition(
        "com.aibao.pitradar.universe",
        "scripts/run_universe_refresh_once.sh",
        "launchd_pitradar_universe.out",
        "launchd_pitradar_universe.err",
        ("08:30",),
        (1, 15),
    ),
    TaskDefinition(
        "com.aibao.pitradar.valuation-radar",
        "scripts/run_valuation_radar_once.sh",
        "launchd_pitradar_valuation_radar.out",
        "launchd_pitradar_valuation_radar.err",
        ("10:30",),
    ),
    TaskDefinition(
        "com.aibao.pitradar.inflection-radar",
        "scripts/run_inflection_radar_once.sh",
        "launchd_pitradar_inflection_radar.out",
        "launchd_pitradar_inflection_radar.err",
        ("10:45",),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and sync pit-radar launchd tasks from config/task_schedule.json.")
    parser.add_argument("--config", default=str(CONFIG_FILE))
    parser.add_argument("--no-launchctl", action="store_true", help="Only write plists; do not bootstrap/bootout launchd.")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_or_create_config(config_path)
    summaries = []
    for definition in TASK_DEFINITIONS:
        task_config = merged_task_config(config, definition)
        plist_path = write_plist(definition, task_config)
        enabled = bool(task_config.get("enabled", True))
        if args.no_launchctl:
            action = "wrote"
        elif enabled:
            install_launch_agent(definition.label, plist_path)
            action = "installed"
        else:
            uninstall_launch_agent(definition.label)
            action = "disabled"
        summaries.append(f"{action} {definition.label} schedule={schedule_label(task_config)}")

    write_merged_config(config_path, config)
    if args.print_summary:
        for line in summaries:
            print(line)


def load_or_create_config(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid task schedule config: {exc}") from exc
        if isinstance(data, dict):
            return data
    return {"timezone": "Asia/Shanghai", "tasks": {}}


def write_merged_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tasks = config.setdefault("tasks", {})
    for definition in TASK_DEFINITIONS:
        tasks[definition.label] = merged_task_config(config, definition)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def merged_task_config(config: dict, definition: TaskDefinition) -> dict:
    tasks = config.setdefault("tasks", {})
    raw = tasks.get(definition.label) if isinstance(tasks.get(definition.label), dict) else {}
    times = raw.get("times", definition.default_times)
    days = raw.get("days", definition.default_days)
    return {
        "enabled": bool(raw.get("enabled", True)),
        "times": normalize_times(times),
        **({"days": normalize_days(days)} if definition.default_days or days else {}),
    }


def write_plist(definition: TaskDefinition, task_config: dict) -> Path:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    script_path = PROJECT_ROOT / definition.script
    plist = {
        "Label": definition.label,
        "ProgramArguments": [
            str(PROJECT_ROOT / "scripts" / "locked_task_runner.sh"),
            definition.label,
            str(script_path),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "StartCalendarInterval": start_calendar_interval(task_config),
        "RunAtLoad": False,
        "StandardOutPath": str(PROJECT_ROOT / "logs" / definition.stdout_name),
        "StandardErrorPath": str(PROJECT_ROOT / "logs" / definition.stderr_name),
    }
    path = LAUNCHD_DIR / f"{definition.label}.plist"
    with path.open("wb") as file:
        plistlib.dump(plist, file, sort_keys=False)
    return path


def start_calendar_interval(task_config: dict):
    times = normalize_times(task_config.get("times") or [])
    days = normalize_days(task_config.get("days") or [])
    intervals = []
    for time_value in times:
        hour, minute = (int(part) for part in time_value.split(":", 1))
        if days:
            for day in days:
                intervals.append({"Day": day, "Hour": hour, "Minute": minute})
        else:
            intervals.append({"Hour": hour, "Minute": minute})
    if not intervals:
        raise SystemExit("At least one schedule time is required for enabled tasks.")
    return intervals[0] if len(intervals) == 1 else intervals


def install_launch_agent(label: str, plist_path: Path) -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = LAUNCH_AGENTS_DIR / plist_path.name
    shutil.copy2(plist_path, target_path)
    target_path.chmod(0o644)
    run_launchctl(["bootout", f"gui/{uid()}/{label}"], check=False)
    run_launchctl(["bootstrap", f"gui/{uid()}", str(target_path)])
    run_launchctl(["enable", f"gui/{uid()}/{label}"])


def uninstall_launch_agent(label: str) -> None:
    target_path = LAUNCH_AGENTS_DIR / f"{label}.plist"
    run_launchctl(["bootout", f"gui/{uid()}/{label}"], check=False)
    target_path.unlink(missing_ok=True)


def run_launchctl(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], check=check, capture_output=True, text=True)


def uid() -> int:
    return int(subprocess.check_output(["id", "-u"], text=True).strip())


def normalize_times(values) -> list[str]:
    if isinstance(values, str):
        items = re.split(r"[,，\s]+", values)
    else:
        items = [str(value) for value in values]
    output = []
    for item in items:
        value = item.strip()
        if not value:
            continue
        if not re.fullmatch(r"\d{1,2}:\d{2}", value):
            raise SystemExit(f"Invalid time: {value}. Use HH:MM.")
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise SystemExit(f"Invalid time: {value}. Use 00:00 to 23:59.")
        output.append(f"{hour:02d}:{minute:02d}")
    if not output:
        raise SystemExit("At least one schedule time is required.")
    return list(dict.fromkeys(output))


def normalize_days(values) -> list[int]:
    if values in (None, ""):
        return []
    if isinstance(values, str):
        items = re.split(r"[,，\s]+", values)
    else:
        items = values
    output = []
    for item in items:
        if item in (None, ""):
            continue
        day = int(item)
        if not 1 <= day <= 31:
            raise SystemExit(f"Invalid day: {day}. Use 1 to 31.")
        output.append(day)
    return sorted(set(output))


def schedule_label(task_config: dict) -> str:
    enabled = bool(task_config.get("enabled", True))
    times = ", ".join(normalize_times(task_config.get("times") or []))
    days = normalize_days(task_config.get("days") or [])
    prefix = "enabled" if enabled else "disabled"
    if days:
        return f"{prefix} monthly days={','.join(str(day) for day in days)} times={times}"
    return f"{prefix} daily times={times}"


if __name__ == "__main__":
    main()
