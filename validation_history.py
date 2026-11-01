"""Orbit v5.9: immutable-looking, venue-separated research observations.

Written to a NEW GitHub branch, not to Telegram/scalp/whale state. The raw
record is the source of truth; paper outcomes are recomputed without lookahead.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import gzip
import io
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from monitor_delivery import DeliveryError, GitHubStateStore


BRANCH = "orbit-validation-history"
PREFIX = ".orbit-validation/days/"
DEFAULT_REPO = "Punnipah/orbit-crypto-signal-lab"
BUCKET_MS = 300_000
MAX_ROWS = 5_000
MAX_GZIP = 900_000
MAX_JSON = 3_500_000
FIELDS = {"t", "v", "s", "st", "sd", "id", "why", "p", "e", "sl", "tp1",
          "tp2", "tp10", "tp10_state", "qty", "risk", "fee", "slip", "spread",
          "regime", "strategy", "bars"}
VENUES = {"BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}


def empty_history() -> dict:
    return {"schema": 1, "rows": []}


def day_path(day: date) -> str:
    if type(day) is not date:
        raise ValueError("UTC calendar date required")
    return PREFIX + day.isoformat() + ".json.gz"


def _numeric(value: object, *, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and
            (not positive or value > 0))


def valid_row(row: object) -> bool:
    if not isinstance(row, dict) or set(row) != FIELDS:
        return False
    if (type(row["t"]) is not int or row["t"] <= 0 or row["v"] not in VENUES
            or not isinstance(row["s"], str)
            or not re.fullmatch(r"[A-Z0-9]{2,18}USDT", row["s"])
            or row["st"] not in {"READY", "WATCH", "WAIT", "RISK_BLOCK", "EXIT_WATCH",
                                 "DATA_UNAVAILABLE"}
            or row["sd"] not in ("LONG", "SHORT", "SELL", "NONE")
            or not isinstance(row["id"], str) or len(row["id"]) > 64
            or not isinstance(row["why"], str) or len(row["why"]) > 180
            or not all(isinstance(row[k], str) and len(row[k]) <= 50
                       for k in ("regime", "strategy", "tp10_state"))):
        return False
    for k in ("p", "e", "sl", "tp1", "tp2", "tp10", "qty", "risk"):
        if row[k] is not None and not _numeric(row[k], positive=True):
            return False
    for k in ("fee", "slip", "spread"):
        if row[k] is not None and (not _numeric(row[k]) or row[k] < 0 or row[k] > 500):
            return False
    if not isinstance(row["bars"], list) or len(row["bars"]) > 7:
        return False
    last = 0
    for candle in row["bars"]:
        if (not isinstance(candle, list) or len(candle) != 5
                or type(candle[0]) is not int or candle[0] <= last
                or candle[0] % 60_000
                or not all(_numeric(x, positive=True) for x in candle[1:])
                or candle[2] < max(candle[1], candle[4])
                or candle[3] > min(candle[1], candle[4])):
            return False
        last = candle[0]
    return row["p"] is not None or row["st"] == "DATA_UNAVAILABLE"


def validate_history(state: object) -> dict:
    if (not isinstance(state, dict) or set(state) != {"schema", "rows"}
            or state["schema"] != 1 or not isinstance(state["rows"], list)
            or len(state["rows"]) > MAX_ROWS):
        raise ValueError("validation archive format/count invalid")
    seen = set()
    for row in state["rows"]:
        if not valid_row(row):
            raise ValueError("validation archive has an invalid observation")
        key = (row["v"], row["s"], row["t"] // BUCKET_MS)
        if key in seen:
            raise ValueError("duplicate interval in validation archive")
        seen.add(key)
    return state


def encode_history(state: dict) -> bytes:
    validate_history(state)
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    if len(raw) > MAX_JSON:
        raise ValueError("validation archive exceeds JSON limit")
    result = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(result) > MAX_GZIP:
        raise ValueError("validation archive exceeds GitHub blob limit")
    return result


def decode_history(raw: bytes) -> dict:
    if len(raw) > MAX_GZIP:
        raise ValueError("validation archive compressed size invalid")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            payload = stream.read(MAX_JSON + 1)
        if len(payload) > MAX_JSON:
            raise ValueError("archive decompressed size invalid")
        return validate_history(json.loads(payload.decode("utf-8")))
    except (OSError, TypeError, ValueError, UnicodeError):
        raise ValueError("validation archive unreadable") from None


def merge_history(existing: dict, additions: list[dict], now: datetime) -> tuple[dict, int]:
    validate_history(existing)
    if now.tzinfo is None:
        raise ValueError("UTC timestamp required")
    today = now.astimezone(timezone.utc).date()
    records = {(r["v"], r["s"], r["t"] // BUCKET_MS): r for r in existing["rows"]}
    changed = 0
    for row in additions:
        if (not valid_row(row) or row["t"] > int(now.timestamp() * 1000) + 5_000
                or datetime.fromtimestamp(row["t"] / 1000, timezone.utc).date() != today):
            raise ValueError("invalid or wrong-day observation")
        key = (row["v"], row["s"], row["t"] // BUCKET_MS)
        prior = records.get(key)
        # Same 5m bucket: allow recovery of a failed source, never replace a
        # valid observation with a later failed fetch or silently overwrite it.
        if prior is None or (prior["st"] == "DATA_UNAVAILABLE" and
                             row["st"] != "DATA_UNAVAILABLE"):
            records[key] = row
            changed += 1
    rows = sorted(records.values(), key=lambda r: (r["t"], r["v"], r["s"]))
    if len(rows) > MAX_ROWS:
        raise ValueError("too many observations for one UTC day")
    return {"schema": 1, "rows": rows}, changed


class GitHubValidationStore(GitHubStateStore):
    def load(self, day: date) -> dict:
        self.day = day
        self.exists = self._request("GET", "/git/ref/heads/" + BRANCH,
                                    missing_ok=True) is not None
        if not self.exists:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        content = self._request("GET", "/contents/" + quote(day_path(day), safe="/") +
                                "?ref=" + BRANCH, missing_ok=True)
        if content is None:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        if content.get("encoding") != "base64" or not isinstance(content.get("content"), str):
            raise DeliveryError("validation archive API format unsupported")
        try:
            blob = base64.b64decode(content["content"], validate=False)
            state = decode_history(blob)
            if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != day
                   for r in state["rows"]):
                raise ValueError("mixed UTC days")
        except (ValueError, TypeError, UnicodeError):
            raise DeliveryError("validation archive unreadable; will NOT overwrite") from None
        self.file_sha, self.current_blob = content.get("sha"), blob
        return state

    def save(self, state: dict) -> bool:
        if not hasattr(self, "day"):
            raise ValueError("load(day) required before save")
        validate_history(state)
        if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != self.day
               for r in state["rows"]):
            raise ValueError("cannot mix UTC days")
        blob = encode_history(state)
        if self.current_blob == blob:
            return False
        if not self.exists:
            self._request("POST", "/git/refs", {"ref": "refs/heads/" + BRANCH,
                                                 "sha": self.default_sha})
            self.exists = True
        body = {"message": "chore(orbit): capture v5.9 paper evidence [skip ci]",
                "content": base64.b64encode(blob).decode("ascii"), "branch": BRANCH}
        if self.file_sha:
            body["sha"] = self.file_sha
        result = self._request("PUT", "/contents/" + quote(day_path(self.day), safe="/"), body)
        if not isinstance(result.get("content"), dict) or not result["content"].get("sha"):
            raise DeliveryError("validation write not acknowledged")
        self.file_sha, self.current_blob = result["content"]["sha"], blob
        return True


def fetch_public_history(days: int = 7, repository: str | None = None) -> dict:
    repository = repository or os.getenv("ORBIT_VALIDATION_REPOSITORY", DEFAULT_REPO)
    if (days not in (1, 7, 30)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise ValueError("invalid validation history selection")
    today = datetime.now(timezone.utc).date()

    def read(day: date):
        url = f"https://raw.githubusercontent.com/{repository}/{BRANCH}/{day_path(day)}"
        try:
            with urlopen(Request(url, headers={"User-Agent": "OrbitValidation/5.9"}),
                         timeout=12) as response:
                raw = response.read(MAX_GZIP + 1)
            state = decode_history(raw)
            if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != day
                   for r in state["rows"]):
                raise ValueError("validation history dates mismatched")
            return state["rows"]
        except HTTPError as exc:
            if exc.code == 404:
                return []
            raise ValueError(f"validation archive HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("ยังโหลด Validation History จาก GitHub ไม่ได้") from None

    dates = [today - timedelta(days=i) for i in range(days)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        chunks = list(pool.map(read, dates))
    rows = [row for chunk in chunks for row in chunk]
    if not rows:
        raise ValueError("ยังไม่มีข้อมูลจริง: กรุณาเปิด Workflow Professional Validation ก่อน")
    rows.sort(key=lambda r: (r["t"], r["v"], r["s"]))
    return {"schema": 1, "rows": rows}
