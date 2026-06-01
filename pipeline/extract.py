"""LLM extraction from earnings transcripts.

Anthropic API, env-gated. No key → returns empty result; pipeline still runs.

Targets: extract {quote, speaker, topic} tuples for AI-relevant statements.
Topics: ai_demand | capex | capacity | model | supply | guidance | other
Also pull structured numeric signals where the model can confidently identify
them in plain text (e.g. "AI run-rate $37B" → ai_arr=37000.0 in millions).
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from .config import ANTHROPIC_API_KEY, LLM_MODEL, has_anthropic


SYSTEM_PROMPT = """You read public-company earnings call transcripts and extract
ONLY AI/data-center/cloud-related signals for a stock-tracking database.

Rules:
- Verbatim quotes only. Do not paraphrase.
- Each quote must be a contiguous span <= 500 characters.
- Skip generic boilerplate ("we are excited about AI"). Keep only quotes that
  contain a fact, number, commitment, or constraint.
- Topics:
    ai_demand    = signs of customer demand for AI services/products
    capex        = capital expenditure plans, $ figures, infra build-out
    capacity     = supply, capacity constraints, GPU/chip availability
    model        = model launches, performance, competitive positioning
    supply       = supply-chain (HBM, CoWoS, ASIC, networking)
    guidance     = forward financial guidance / next-quarter / FY outlook
    other        = anything else AI-related but not above

Also extract structured signals when EXPLICITLY stated in the text:
    cloud_revenue_yoy_pct   (e.g. "Cloud grew 63%" → 63.0)
    ai_arr_usd_millions     (e.g. "$37 billion run rate" → 37000)
    capex_quarter_usd_millions
    capex_full_year_low / capex_full_year_high
    capacity_constrained    (boolean: true if mgmt explicitly says capacity is
                             insufficient / demand exceeds supply)

Return STRICT JSON with this shape:
{
  "quotes": [
    {"quote": "...", "speaker": "Satya Nadella", "topic": "capex"}
  ],
  "signals": {
    "cloud_revenue_yoy_pct": 63.0,
    "ai_arr_usd_millions": 37000,
    "capex_quarter_usd_millions": 40000,
    "capex_full_year_low": null,
    "capex_full_year_high": null,
    "capacity_constrained": true
  }
}

If a signal is not explicit in the text, use null. Do not invent.
"""


@dataclass
class Quote:
    quote: str
    speaker: str = ""
    topic: str = "other"


@dataclass
class ExtractionResult:
    quotes: list[Quote] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    raw_response: str = ""

    def merge_into_earnings_row(self, row: dict) -> dict:
        """Apply extracted signals to an earnings dict in place; return it.
        Only fills fields that are currently None/missing."""
        s = self.signals or {}

        def setn(key, val, scale_pct=False):
            if val is None:
                return
            if scale_pct:
                val = float(val) / 100.0
            if row.get(key) is None:
                row[key] = val

        setn("cloud_revenue_yoy", s.get("cloud_revenue_yoy_pct"), scale_pct=True)
        setn("ai_arr", s.get("ai_arr_usd_millions"))
        setn("capex_quarter", s.get("capex_quarter_usd_millions"))
        setn("capex_full_year_low", s.get("capex_full_year_low"))
        setn("capex_full_year_high", s.get("capex_full_year_high"))
        return row


def extract_from_transcript(transcript_text: str, ticker: str = "",
                            fiscal_period: str = "") -> ExtractionResult:
    """Run LLM extraction. Returns empty result if no API key."""
    if not has_anthropic() or not transcript_text.strip():
        return ExtractionResult()
    try:
        import anthropic  # type: ignore
    except ImportError:
        return ExtractionResult()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_msg = (
        f"Ticker: {ticker}\nFiscal period: {fiscal_period}\n\n"
        f"--- Transcript ---\n{transcript_text}\n--- End ---\n\n"
        "Return only the JSON object."
    )
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return _parse_response(text)


def _parse_response(text: str) -> ExtractionResult:
    out = ExtractionResult(raw_response=text)
    # Find first {...} JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return out
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return out
    for q in data.get("quotes", []) or []:
        if not isinstance(q, dict) or not q.get("quote"):
            continue
        out.quotes.append(Quote(
            quote=q["quote"].strip(),
            speaker=(q.get("speaker") or "").strip(),
            topic=(q.get("topic") or "other").strip(),
        ))
    out.signals = data.get("signals") or {}
    return out
