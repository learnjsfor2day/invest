from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from pit_radar.collectors.base import CollectionContext
from pit_radar.services.ingest import IngestService

from tests.test_macro_events import MacroPayloadCollector


def _load_reminder_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "macro_event_reminder.py"
    spec = importlib.util.spec_from_file_location("macro_event_reminder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_macro_reminder_uses_latest_event_version(session, store, engine, monkeypatch):
    reminder = _load_reminder_module()
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(reminder, "create_session_factory", lambda: factory)

    now = datetime(2026, 7, 14, 8, tzinfo=UTC)
    service = IngestService(session, store)
    base = {
        "date": "2026-07-16 12:30:00",
        "event": "Core CPI MoM (Jun)",
        "country": "US",
        "currency": "USD",
        "impact": "High",
        "estimate": "0.2%",
        "previous": "0.1%",
    }
    changed = dict(base, estimate="0.3%")
    service.ingest(MacroPayloadCollector({"events": [base]}), CollectionContext("live", ["US"], now))
    service.ingest(MacroPayloadCollector({"events": [changed]}), CollectionContext("live", ["US"], now + timedelta(hours=1)))
    session.commit()

    events = reminder.upcoming_latest_macro_events(now, 3, ["US"], ["High"])

    assert len(events) == 1
    assert events[0].estimate_raw == "0.3%"
