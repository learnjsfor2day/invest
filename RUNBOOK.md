# RUNBOOK — AI 产业链财报监控 v0

A minimal, env-gated pipeline. Current setup: **FMP key set**, no LLM, no Lark webhook. Free SEC EDGAR + yfinance work for free. Add the rest incrementally.

> Note: FMP migrated v3 → `/stable/` on 2025-08-31. `pipeline/sources.py` is on the new endpoints. Earnings calendar + fundamentals work on the free key; **transcripts require a paid tier** (HTTP 402 → empty). Since you're doing analysis by hand for now, that's not a blocker.

## What it does

Per ticker on `company_list.jsonl` (235 companies):

1. Pull latest quarterly fundamentals (FMP, optional)
2. Pull latest earnings call transcript (FMP, optional)
3. LLM-extract verbatim AI/capex/capacity quotes + structured numeric signals (Anthropic, optional)
4. Upsert into SQLite `earnings` table
5. Pull T+1 / T+3 stock reaction (yfinance, free)
6. Classify into Tier 1–4 via deterministic rules in `pipeline/tiers.py`
7. Cross-ticker: poll SEC EDGAR for new 8-K filings (free), record alerts, push to 飞书

## Daily workflow (your current setup)

```bash
set -a; source .env; set +a

# What's reporting earnings on my watchlist in the next N days?
python scripts/upcoming_earnings.py 14

# After a target reports, run the pipeline — pulls fundamentals, prices, 8-Ks
python -m pipeline.orchestrate GOOGL MSFT

# Then ping Claude Code with the transcript or report URL for manual analysis
```

Without an LLM key, the pipeline:
- Pulls income-statement numbers (revenue, margins, EPS) ✓
- Pulls 8-K filings ✓
- Computes T+1 / T+3 price reaction ✓
- Classifies Tier 1–4 from numeric signals only (no quote/capacity signals)
- Skips transcript extraction (call Claude Code manually instead)

## One-time setup

```bash
# 1. (optional) install the two optional deps
pip install -r requirements.txt

# 2. copy env template; leave keys blank for v0
cp .env.example .env

# 3. initialize DB and load 235-company watchlist + migrate the existing CSV
python scripts/init_db.py
# expect: [load_pool] loaded 235  [migrate_csv] migrated 2  [summary] ...
```

The DB lives at `data/invest.db` (created on first run). Schema in `pipeline/db.py`.

## Running the pipeline

```bash
# load env (only when you've added keys)
set -a; source .env; set +a

# default: GOOGL + MSFT
python -m pipeline.orchestrate

# any tickers
python -m pipeline.orchestrate GOOGL MSFT NVDA AVGO TSM
```

Without keys you get: SEC 8-K alerts + price reaction. That's it. With FMP: + fundamentals + transcripts. With Anthropic: + structured quote/signal extraction. With Lark: + push to 飞书.

## Adding keys (suggested order)

1. **FMP** — biggest single unlock (fundamentals + transcripts + earnings calendar)
2. **Anthropic** — turns transcripts into quotes + signals
3. **Lark webhook** — push instead of stdout
4. **SEC_USER_AGENT** — set to your email; SEC requests it but doesn't enforce

Edit `.env`, `set -a; source .env; set +a`, re-run.

## Scheduling

Quarterly is too coarse for 8-K alerts; daily is right.

### macOS (launchd) — sample plist

Save as `~/Library/LaunchAgents/com.invest.monitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.invest.monitor</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd /Users/gerui1/invest- && set -a && source .env && set +a && /usr/bin/env python3 -m pipeline.orchestrate >> logs/run.log 2>&1</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer>
  </dict>
  <key>RunAtLoad</key><false/>
</dict></plist>
```

Then: `launchctl load ~/Library/LaunchAgents/com.invest.monitor.plist`.

### Linux (cron)

```cron
30 7 * * * cd ~/invest- && set -a && . ./.env && set +a && python3 -m pipeline.orchestrate >> logs/run.log 2>&1
```

## Useful queries

```bash
# all Tier 1 tickers from the latest run
sqlite3 data/invest.db "SELECT ticker, fiscal_period, tier, reason FROM tiers
  WHERE tier=1 ORDER BY classified_at DESC LIMIT 20;"

# this week's 8-K alerts
sqlite3 data/invest.db "SELECT ticker, filing_date, title, url FROM alerts
  WHERE filing_date >= date('now','-7 days') ORDER BY filing_date DESC;"

# AI/capex quotes for a ticker
sqlite3 data/invest.db "SELECT speaker, topic, quote FROM quotes
  WHERE ticker='MSFT' ORDER BY captured_at DESC LIMIT 20;"
```

## Tier rules (in one place)

`pipeline/tiers.py`:

| Signal               | Threshold                    |
| -------------------- | ---------------------------- |
| `cloud_revenue_yoy`  | ≥ 30%                        |
| `ai_arr_yoy`         | ≥ 50%                        |
| `backlog_rpo_qoq`    | ≥ 20%                        |
| `revenue_yoy`        | ≥ 20%                        |
| `capex_raised`       | vs prior quarter (boolean)   |
| `capacity_constrained` | from LLM extraction        |

- ≥ 3 matches → **Tier 1** (重点跟踪)
- 1–2 matches → **Tier 2** (等待验证)
- 0 matches + 3-month return ≥ 30% → **Tier 3** (已反应)
- 0 matches + flat → **Tier 4** (噪音)

Tweak in one spot if your bar shifts.

## Files

```
company_list.jsonl    235-company AI watchlist (line-per-record, agent-friendly)
financial_data.csv    legacy CSV (migrated into DB by init_db.py)
data/invest.db        SQLite — companies, earnings, quotes, tiers, alerts, runs
pipeline/
  config.py           env-var loader, has_fmp/has_anthropic/has_lark
  db.py               schema + CRUD
  sources.py          SEC EDGAR (free), FMP (env-gated), yfinance (optional)
  extract.py          Anthropic LLM extraction
  tiers.py            deterministic 4-tier classification
  notify.py           stdout + Lark webhook
  orchestrate.py      end-to-end: update_company / poll_8k_alerts / run_pipeline
scripts/init_db.py    one-time DB init + CSV/JSONL migration
```

## Known limits (v0)

- FMP quarterly income statement doesn't return YoY directly — `revenue_yoy` left None unless an LLM signal fills it.
- 8-K poll dedupes by accession number per ticker.
- yfinance occasionally rate-limits silently — failures are logged into the per-run notes, not retried.
- A-shares / Tushare / DART / FinMind are NOT implemented yet (v0 scope is US-listed).
