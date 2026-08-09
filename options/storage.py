from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
TRADES_FILE = DATA_DIR / "trades.csv"
REVIEWS_FILE = DATA_DIR / "reviews.csv"
ACCOUNT_SNAPSHOTS_FILE = DATA_DIR / "account_snapshots.csv"


TRADE_COLUMNS = [
    "id",
    "trade_date",
    "ticker",
    "option_type",
    "expiry",
    "strike",
    "action",
    "contracts",
    "premium",
    "spot",
    "iv",
    "fees",
    "strategy",
    "thesis",
    "tags",
    "created_at",
]

REVIEW_COLUMNS = [
    "id",
    "review_date",
    "ticker",
    "contract_key",
    "pnl",
    "pnl_pct",
    "setup",
    "entry_reason",
    "exit_reason",
    "rule_followed",
    "emotion_score",
    "execution_score",
    "mistake_tags",
    "lessons",
    "next_action",
    "created_at",
]

ACCOUNT_SNAPSHOT_COLUMNS = [
    "id",
    "record_date",
    "account",
    "net_liq",
    "cash",
    "buying_power",
    "margin_used",
    "deposit",
    "withdrawal",
    "realized_pnl",
    "notes",
    "created_at",
]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_trades() -> pd.DataFrame:
    return _load_csv(TRADES_FILE, TRADE_COLUMNS)


def save_trades(df: pd.DataFrame) -> None:
    ensure_data_dir()
    _normalize_trades(df).to_csv(TRADES_FILE, index=False)


def append_trade(values: dict[str, object]) -> dict[str, object]:
    row = {column: values.get(column, "") for column in TRADE_COLUMNS}
    row["id"] = row["id"] or uuid4().hex
    row["created_at"] = row["created_at"] or datetime.now().isoformat(timespec="seconds")
    df = load_trades()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_trades(df)
    return row


def load_reviews() -> pd.DataFrame:
    return _load_csv(REVIEWS_FILE, REVIEW_COLUMNS)


def save_reviews(df: pd.DataFrame) -> None:
    ensure_data_dir()
    _normalize_reviews(df).to_csv(REVIEWS_FILE, index=False)


def append_review(values: dict[str, object]) -> dict[str, object]:
    row = {column: values.get(column, "") for column in REVIEW_COLUMNS}
    row["id"] = row["id"] or uuid4().hex
    row["created_at"] = row["created_at"] or datetime.now().isoformat(timespec="seconds")
    df = load_reviews()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_reviews(df)
    return row


def load_account_snapshots() -> pd.DataFrame:
    return _load_csv(ACCOUNT_SNAPSHOTS_FILE, ACCOUNT_SNAPSHOT_COLUMNS)


def save_account_snapshots(df: pd.DataFrame) -> None:
    ensure_data_dir()
    _normalize_account_snapshots(df).to_csv(ACCOUNT_SNAPSHOTS_FILE, index=False)


def append_account_snapshot(values: dict[str, object]) -> dict[str, object]:
    row = {column: values.get(column, "") for column in ACCOUNT_SNAPSHOT_COLUMNS}
    row["id"] = row["id"] or uuid4().hex
    row["created_at"] = row["created_at"] or datetime.now().isoformat(timespec="seconds")
    df = load_account_snapshots()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_account_snapshots(df)
    return row


def contract_key(ticker: str, expiry: object, strike: object, option_type: str) -> str:
    return f"{str(ticker).upper()} {expiry} {float(strike):.2f} {option_type.upper()}"


def compute_positions(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = _normalize_trades(trades)
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()

    trades = trades.sort_values(["trade_date", "created_at", "id"], na_position="last")
    states: dict[tuple[str, str, str, float], dict[str, object]] = {}
    realized_rows: list[dict[str, object]] = []

    for _, row in trades.iterrows():
        key = (row["ticker"], row["option_type"], row["expiry"], float(row["strike"]))
        state = states.setdefault(
            key,
            {
                "ticker": row["ticker"],
                "option_type": row["option_type"],
                "expiry": row["expiry"],
                "strike": float(row["strike"]),
                "long_qty": 0,
                "long_avg": 0.0,
                "short_qty": 0,
                "short_avg": 0.0,
                "realized_pnl": 0.0,
                "last_spot": 0.0,
                "last_iv": 0.0,
                "strategy": row["strategy"],
                "tags": row["tags"],
            },
        )
        qty = int(row["contracts"])
        premium = float(row["premium"])
        fees = float(row["fees"])
        if row["spot"]:
            state["last_spot"] = float(row["spot"])
        if row["iv"]:
            state["last_iv"] = float(row["iv"])

        if row["action"] == "买入开仓":
            total_cost = float(state["long_avg"]) * int(state["long_qty"]) * 100 + premium * qty * 100 + fees
            state["long_qty"] = int(state["long_qty"]) + qty
            state["long_avg"] = total_cost / (int(state["long_qty"]) * 100)
        elif row["action"] == "卖出平仓":
            closed = min(qty, int(state["long_qty"]))
            realized = (premium - float(state["long_avg"])) * closed * 100 - fees
            basis = float(state["long_avg"]) * closed * 100
            state["long_qty"] = int(state["long_qty"]) - closed
            state["realized_pnl"] = float(state["realized_pnl"]) + realized
            realized_rows.append(_realized_row(row, closed, realized, "long", basis))
        elif row["action"] == "卖出开仓":
            total_credit = float(state["short_avg"]) * int(state["short_qty"]) * 100 + premium * qty * 100 - fees
            state["short_qty"] = int(state["short_qty"]) + qty
            state["short_avg"] = total_credit / (int(state["short_qty"]) * 100)
        elif row["action"] == "买入平仓":
            closed = min(qty, int(state["short_qty"]))
            realized = (float(state["short_avg"]) - premium) * closed * 100 - fees
            basis = float(state["short_avg"]) * closed * 100
            state["short_qty"] = int(state["short_qty"]) - closed
            state["realized_pnl"] = float(state["realized_pnl"]) + realized
            realized_rows.append(_realized_row(row, closed, realized, "short", basis))

    position_rows: list[dict[str, object]] = []
    for state in states.values():
        base = {
            "ticker": state["ticker"],
            "option_type": state["option_type"],
            "expiry": state["expiry"],
            "strike": state["strike"],
            "contract_key": contract_key(state["ticker"], state["expiry"], state["strike"], state["option_type"]),
            "last_spot": state["last_spot"],
            "last_iv": state["last_iv"],
            "strategy": state["strategy"],
            "tags": state["tags"],
            "realized_pnl": state["realized_pnl"],
        }
        if int(state["long_qty"]) > 0:
            position_rows.append({**base, "direction": "long", "contracts": state["long_qty"], "avg_price": state["long_avg"]})
        if int(state["short_qty"]) > 0:
            position_rows.append({**base, "direction": "short", "contracts": state["short_qty"], "avg_price": state["short_avg"]})

    return pd.DataFrame(position_rows), pd.DataFrame(realized_rows)


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    ensure_data_dir()
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    return df[columns]


def _normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in TRADE_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    output = output[TRADE_COLUMNS]
    text_columns = ["id", "trade_date", "ticker", "option_type", "expiry", "action", "strategy", "thesis", "tags", "created_at"]
    for column in text_columns:
        output[column] = output[column].fillna("").astype(str)
    output["ticker"] = output["ticker"].str.upper().str.strip()
    output["option_type"] = output["option_type"].str.lower().str.strip()
    output["action"] = output["action"].str.strip()
    for column in ["strike", "contracts", "premium", "spot", "iv", "fees"]:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    output["contracts"] = output["contracts"].astype(int)
    return output


def _normalize_reviews(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in REVIEW_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    output = output[REVIEW_COLUMNS]
    for column in ["pnl", "pnl_pct", "emotion_score", "execution_score"]:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    return output


def _normalize_account_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in ACCOUNT_SNAPSHOT_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    output = output[ACCOUNT_SNAPSHOT_COLUMNS]
    text_columns = ["id", "record_date", "account", "notes", "created_at"]
    for column in text_columns:
        output[column] = output[column].fillna("").astype(str)
    output["account"] = output["account"].str.strip()
    for column in ["net_liq", "cash", "buying_power", "margin_used", "deposit", "withdrawal", "realized_pnl"]:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    return output


def _realized_row(row: pd.Series, closed: int, realized: float, direction: str, basis: float) -> dict[str, object]:
    return {
        "trade_date": row["trade_date"],
        "ticker": row["ticker"],
        "contract_key": contract_key(row["ticker"], row["expiry"], row["strike"], row["option_type"]),
        "direction": direction,
        "contracts": closed,
        "premium": row["premium"],
        "cost_basis": basis,
        "realized_pnl": realized,
        "pnl_pct": realized / basis * 100 if basis else 0,
    }
