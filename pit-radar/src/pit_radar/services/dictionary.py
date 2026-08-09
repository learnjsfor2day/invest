from __future__ import annotations

import csv
from pathlib import Path

from pit_radar.db.base import Base
from pit_radar.db.models import *  # noqa: F401,F403
from pit_radar.ui.field_labels_zh import FIELD_LABELS_ZH


def rows() -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: f"{t.schema}.{t.name}"):
        for column in table.columns:
            table_name = f"{table.schema}.{table.name}"
            label = FIELD_LABELS_ZH.get(f"{table_name}.{column.name}", FIELD_LABELS_ZH.get(column.name, {}))
            output.append(
                {
                    "table": table_name,
                    "field": column.name,
                    "name_zh": label.get("name", column.comment or column.name),
                    "description_zh": label.get("description", column.comment or ""),
                    "data_type": str(column.type),
                    "unit": "",
                    "example": "",
                }
            )
    return output


def export_dictionary(output: Path, fmt: str = "markdown") -> None:
    data = rows()
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        with output.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
        return

    lines = ["# PIT Radar 数据字典", "", "| 表 | 英文字段 | 中文名称 | 中文解释 | 数据类型 |", "|---|---|---|---|---|"]
    for item in data:
        lines.append(
            f"| {item['table']} | `{item['field']}` | {item['name_zh']} | {item['description_zh']} | `{item['data_type']}` |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
