from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from pit_radar.db.models import DatasetCoverage
from pit_radar.time import utc_now


def _load_backfill_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_fmp_enrichment.py"
    spec = importlib.util.spec_from_file_location("backfill_fmp_enrichment", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_coverage_classifies_no_data_and_transient_errors():
    backfill = _load_backfill_module()

    assert backfill.classify_coverage_status("MU: no financial facts returned") == "no_data"
    assert backfill.classify_coverage_status("ABC: FMP /stable/ratios failed: 429 rate limited") == "transient_failed"


def test_resume_plan_skips_recent_no_data_coverage(engine, session, monkeypatch):
    backfill = _load_backfill_module()
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(backfill, "create_session_factory", lambda: factory)

    now = utc_now()
    session.add(
        DatasetCoverage(
            source_code="fmp",
            dataset_code="financials",
            symbol="ZZZ",
            status="no_data",
            last_checked_at=now,
            next_check_after=now + timedelta(days=30),
            failure_count=0,
        )
    )
    session.commit()

    plan = backfill.plan_symbols_for_task(["MU", "ZZZ"], "financials")

    assert plan.pending == ["MU"]
    assert plan.skipped_coverage == 1
