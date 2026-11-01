"""Separate, compressed UTC-day archives on an independent GitHub branch.

The UI reads at most 30 days of real 5m observations after deployment. Older
archive files are NOT deleted. This is not a historical backfill, trade ledger,
or Win Rate / paper-trade journal; it is separate from the app and Telegram.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from monitor_delivery import DeliveryError, GitHubStateStore
from whale_footprint import WhaleFootprint


BRANCH = "orbit-whale-history"
PATH_PREFIX = ".orbit-whale/days/"
DAYS = 30
INTERVAL_MS = 300_000
MAX_ENTRIES = 50_000  # 30 days * 5 venues/symbols * 288 5m buckets.
# Each day is its own small file; avoid GitHub Contents API's >1MB blob limit.
MAX_GZIP = 900_000
MAX_JSON = 3_000_000
DEFAULT_PUBLIC_REPO = "Punnipah/orbit-crypto-signal-lab"


def empty_history() -> dict:
    return {"schema": 1, "rows": []}


def day_path(day: date) -> str:
    if not isinstance(day, date):
        raise ValueError("history date required")
    return PATH_PREFIX + day.isoformat() + ".json.gz"


def make_row(ob: WhaleFootprint) -> dict:
    timestamp_ms = int(ob.checked_at.timestamp() * 1000)
    if ob.checked_at.tzinfo is None or timestamp_ms <= 0:
        raise ValueError("history timestamp requires UTC timezone")
    return {
        "t": timestamp_ms // INTERVAL_MS * INTERVAL_MS,
        "v": ob.venue, "s": ob.symbol, "p": round(ob.price, 12),
        "d": None if ob.delta_5m_usdt is None else round(ob.delta_5m_usdt, 2),
        "b": None if ob.taker_buy_share_5m is None else round(ob.taker_buy_share_5m, 4),
        "x": round(ob.volume_ratio_5m, 3), "g": ob.classification,
        "q": round(ob.bid_depth_share, 4),
        "lb": None if ob.prints is None else round(ob.prints.buy_usdt, 2),
        "ls": None if ob.prints is None else round(ob.prints.sell_usdt, 2),
    }


def _valid_row(row: object) -> bool:
    if not isinstance(row, dict) or set(row) != {"t", "v", "s", "p", "d", "b", "x", "g", "q", "lb", "ls"}:
        return False
    if (type(row["t"]) is not int or row["t"] <= 0 or row["t"] % INTERVAL_MS
            or row["v"] not in {"BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}
            or not isinstance(row["s"], str) or not re.fullmatch(r"[A-Z0-9]{2,18}USDT", row["s"])
            or not isinstance(row["g"], str) or row["g"] not in {
                "FLOW_UNAVAILABLE", "POSSIBLE_BID_ABSORPTION", "POSSIBLE_ASK_ABSORPTION",
                "BUY_PRESSURE", "SELL_PRESSURE", "MIXED"}):
        return False
    for key in ("p", "x", "q"):
        if type(row[key]) not in (float, int) or not math.isfinite(row[key]):
            return False
    if row["p"] <= 0 or row["x"] < 0 or not 0 <= row["q"] <= 1:
        return False
    for key in ("d", "b", "lb", "ls"):
        if row[key] is not None and (type(row[key]) not in (float, int) or
                                     not math.isfinite(row[key])):
            return False
    return (row["b"] is None or 0 <= row["b"] <= 1) and all(
        row[key] is None or row[key] >= 0 for key in ("lb", "ls"))


def validate_history(state: object) -> dict:
    if (not isinstance(state, dict) or set(state) != {"schema", "rows"}
            or state.get("schema") != 1 or not isinstance(state["rows"], list)
            or len(state["rows"]) > MAX_ENTRIES):
        raise ValueError("whale history format/count invalid")
    seen = set()
    for row in state["rows"]:
        if not _valid_row(row):
            raise ValueError("invalid whale history row")
        key = (row["v"], row["s"], row["t"])
        if key in seen:
            raise ValueError("duplicate whale history interval")
        seen.add(key)
    return state


def encode_history(state: dict) -> bytes:
    validate_history(state)
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_JSON:
        raise ValueError("whale history exceeds size limit")
    data = gzip.compress(payload, compresslevel=6, mtime=0)
    if len(data) > MAX_GZIP:
        raise ValueError("compressed whale history exceeds size limit")
    return data


def decode_history(data: bytes) -> dict:
    if len(data) > MAX_GZIP:
        raise ValueError("compressed history too large")
    try:
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            payload = stream.read(MAX_JSON + 1)
        if len(payload) > MAX_JSON:
            raise ValueError("decompressed history too large")
        return validate_history(json.loads(payload.decode("utf-8")))
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise ValueError(f"whale history is corrupt: {type(exc).__name__}") from None


def merge_history(state: dict, additions: list[dict], now: datetime) -> tuple[dict, int]:
    validate_history(state)
    if now.tzinfo is None:
        raise ValueError("timezone required")
    latest = int(now.timestamp() * 1000)
    earliest = latest - DAYS * 86_400_000
    records = {(r["v"], r["s"], r["t"]): r for r in state["rows"]
               if r["t"] >= earliest}
    added = 0
    for row in additions:
        if not _valid_row(row) or not earliest <= row["t"] <= latest:
            raise ValueError("new whale observation invalid or future-dated")
        key = (row["v"], row["s"], row["t"])
        if key not in records:
            records[key] = row
            added += 1
    rows = sorted(records.values(), key=lambda r: (r["t"], r["v"], r["s"]))
    if len(rows) > MAX_ENTRIES:
        rows = rows[-MAX_ENTRIES:]
    return {"schema": 1, "rows": rows}, added


class GitHubWhaleHistoryStore(GitHubStateStore):
    """Writes only the UTC daily object on BRANCH, never the app branch."""

    def load(self, day: date) -> dict:
        self.day = day
        path = day_path(day)
        self.exists = self._request("GET", "/git/ref/heads/" + BRANCH,
                                    missing_ok=True) is not None
        if not self.exists:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        data = self._request("GET", "/contents/" + quote(path, safe="/") +
                             "?ref=" + BRANCH, missing_ok=True)
        if data is None:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            raise DeliveryError("whale history API encoding unsupported")
        try:
            payload = base64.b64decode(data["content"], validate=False)
            state = decode_history(payload)
        except (ValueError, TypeError, UnicodeError):
            raise DeliveryError("whale history unreadable; refusing overwrite") from None
        self.file_sha, self.current_blob = data.get("sha"), payload
        return state

    def save(self, state: dict) -> bool:
        if not hasattr(self, "day"):
            raise ValueError("load(day) required before save")
        if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != self.day
               for r in state["rows"]):
            raise ValueError("cannot mix history records from different UTC days")
        data = encode_history(state)
        if data == self.current_blob:
            return False
        if not self.exists:
            self._request("POST", "/git/refs", {"ref": "refs/heads/" + BRANCH,
                                                  "sha": self.default_sha})
            self.exists = True
        body = {"message": "chore(orbit): collect anonymous whale footprint [skip ci]",
                "content": base64.b64encode(data).decode("ascii"), "branch": BRANCH}
        if self.file_sha:
            body["sha"] = self.file_sha
        result = self._request("PUT", "/contents/" +
                               quote(day_path(self.day), safe="/"), body)
        if not isinstance(result.get("content"), dict) or not result["content"].get("sha"):
            raise DeliveryError("whale history write not acknowledged")
        self.file_sha, self.current_blob = result["content"]["sha"], data
        return True


def fetch_public_history(repository: str | None = None, days: int = 7) -> dict:
    """Read 1, 7 or 30 UTC daily files from a PUBLIC repo; never infer gaps."""
    repository = repository or os.getenv("ORBIT_WHALE_REPOSITORY", DEFAULT_PUBLIC_REPO)
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or days not in (1, 7, 30)):
        raise ValueError("invalid public history repository")
    today = datetime.now(timezone.utc).date()

    def one_day(day: date) -> dict | None:
        url = f"https://raw.githubusercontent.com/{repository}/{BRANCH}/{day_path(day)}"
        request = Request(url, headers={"User-Agent": "OrbitWhaleHistory/5.8.5"})
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise ValueError("history HTTP response not OK")
                raw = response.read(MAX_GZIP + 1)
            value = decode_history(raw)
            if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != day
                   for r in value["rows"]):
                raise ValueError("history file contains a different day's data")
            return value
        except HTTPError as exc:
            if exc.code == 404:
                return None  # normal before first run or on quiet days
            raise ValueError(f"public whale history HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("ยังอ่านข้อมูลประวัติจาก GitHub ไม่ได้") from None

    calendar = [today - timedelta(days=i) for i in range(days)]
    # Bounded parallel reads make the 30-day view usable on mobile.
    with ThreadPoolExecutor(max_workers=6) as pool:
        chunks = list(pool.map(one_day, calendar))
    present = [x for x in chunks if x is not None]
    if not present:
        raise ValueError("ยังไม่มีประวัติ: ต้องเปิด Workflow Whale ก่อน")
    state = {"schema": 1, "rows": [r for day in present for r in day["rows"]]}
    return validate_history(state)


def history_for(state: dict, venue: str, symbol: str) -> list[dict]:
    validate_history(state)
    return [r for r in state["rows"] if r["v"] == venue and r["s"] == symbol]
