from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path


def _load_daily_batch_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "daily_fmp_batch.py"
    spec = importlib.util.spec_from_file_location("daily_fmp_batch", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_previous_new_york_business_day_from_beijing_today():
    module = _load_daily_batch_module()
    now = datetime(2026, 7, 14, 13, 0, tzinfo=UTC)
    assert module.previous_new_york_business_day(now).isoformat() == "2026-07-13"


def test_previous_new_york_business_day_after_new_york_close():
    module = _load_daily_batch_module()
    now = datetime(2026, 7, 14, 23, 30, tzinfo=UTC)
    assert module.previous_new_york_business_day(now).isoformat() == "2026-07-14"


def test_previous_new_york_business_day_on_weekend_after_friday_close():
    module = _load_daily_batch_module()
    now = datetime(2026, 7, 19, 14, 0, tzinfo=UTC)
    assert module.previous_new_york_business_day(now).isoformat() == "2026-07-17"


def test_normalize_symbols_dedupes_and_ignores_comments():
    module = _load_daily_batch_module()
    assert module.normalize_symbols([" mu ", "AAPL", "# comment", "MU", "nvda note"]) == ["MU", "AAPL", "NVDA"]


def test_read_symbol_file_ignores_comma_separated_comment_lines(tmp_path):
    module = _load_daily_batch_module()
    path = tmp_path / "symbols.txt"
    path.write_text("# Criteria: exchanges=NASDAQ,NYSE,AMEX\nAAPL\nMU,NVDA\n", encoding="utf-8")

    assert module.read_symbol_file(path) == ["AAPL", "MU", "NVDA"]
