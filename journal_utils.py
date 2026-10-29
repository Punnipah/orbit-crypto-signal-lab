"""Local/session-only signal journal import/export; no accounts or cloud writes.

The journal records *observed signals*, not executed transactions. No profit
metric should ever be calculated from these rows as if a real fill occurred.
"""

from __future__ import annotations

from io import BytesIO
import csv

import pandas as pd


MAX_BYTES = 2_000_000
MAX_ROWS = 10_000
CORE = {"observed_at_th", "symbol", "mtf_signal", "entry_status"}


def import_signal_journal(contents: bytes) -> list[dict]:
    if not contents or len(contents) > MAX_BYTES:
        raise ValueError("CSV ต้องไม่ว่างและไม่เกิน 2 MB")
    try:
        table = pd.read_csv(BytesIO(contents), encoding="utf-8-sig", dtype=str,
                            keep_default_na=False)
    except (UnicodeError, ValueError, pd.errors.ParserError) as exc:
        raise ValueError("อ่าน CSV ไม่ได้") from exc
    if not CORE.issubset(table.columns) or len(table) > MAX_ROWS:
        raise ValueError("CSV ไม่มีหัวตาราง Orbit Paper Journal หรือมีรายการเกิน 10,000")
    if table.columns.duplicated().any():
        raise ValueError("CSV มีหัวคอลัมน์ซ้ำ")
    records = []
    for row in table.to_dict("records"):
        if not row["symbol"].isascii() or not row["symbol"].isalnum() or len(row["symbol"]) > 24:
            raise ValueError("ชื่อเหรียญใน CSV ไม่ถูกต้อง")
        if row["mtf_signal"] not in ("BUY", "WAIT") or row["entry_status"] not in (
            "READY", "WAIT_ENTRY", "WAIT_SIGNAL"):
            raise ValueError("สถานะสัญญาณใน CSV ไม่ถูกต้อง")
        records.append(row)
    return records


def combine_journal(old: list[dict], new: list[dict]) -> list[dict]:
    """De-duplicate by stable observation identity, leaving newest records."""
    values = {}
    for row in old + new:
        identity = (str(row.get("observed_at_th", "")), str(row.get("symbol", "")),
                    str(row.get("entry_status", "")))
        values[identity] = row
    if len(values) > MAX_ROWS:
        raise ValueError("จำนวนบันทึกเกิน 10,000")
    return list(values.values())


def export_signal_journal(records: list[dict]) -> bytes:
    if not records:
        return b""
    frame = pd.DataFrame(records)
    # Spreadsheet programs can interpret cells beginning =,+,-,@ as formulas.
    # Neutralize external strings on export; numeric cells retain their values.
    for column in frame.columns:
        frame[column] = frame[column].map(
            lambda value: "'" + value if isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return frame.to_csv(index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8-sig")
