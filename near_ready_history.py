"""Strict separate GitHub archive for v5.9.1 near-ready research events.

No changes to the v5.9 validation archive format, delivery or trade alerts.
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
from near_ready_tracker import CHECKS, NEAR_STATE
from validation_history import BRANCH, DEFAULT_REPO, VENUES


PREFIX = ".orbit-validation/near-ready/"
MAX_ROWS = 5_000
MAX_GZIP = 500_000
MAX_JSON = 1_600_000
FIELDS = {"t", "v", "s", "sd", "z", "lo", "hi", "p", "fail", "checks", "st"}


def day_path(day: date) -> str:
    if type(day) is not date:
        raise ValueError("UTC calendar date required")
    return PREFIX + day.isoformat() + ".json.gz"


def empty_history() -> dict:
    return {"schema": 1, "rows": []}


def valid_event(row: object) -> bool:
    if not isinstance(row, dict) or set(row) != FIELDS:
        return False
    if (type(row["t"]) is not int or row["t"] <= 0 or row["v"] not in VENUES
            or not isinstance(row["s"], str) or not re.fullmatch(r"[A-Z0-9]{2,18}USDT", row["s"])
            or row["sd"] not in ("LONG", "SHORT") or row["st"] != NEAR_STATE
            or not isinstance(row["z"], str) or len(row["z"]) > 35
            or row["fail"] not in CHECKS
            or not isinstance(row["checks"], list) or len(row["checks"]) != 5
            or any(type(x) is not bool for x in row["checks"])
            or sum(row["checks"]) != 4 or row["checks"][CHECKS.index(row["fail"])]):
        return False
    if row["v"] == "BINANCE_TH_SPOT" and row["sd"] == "SHORT":
        return False
    return (all(type(row[k]) in (int, float) and math.isfinite(row[k]) and row[k] > 0
                for k in ("p", "lo", "hi")) and row["lo"] <= row["hi"])


def validate(state: object) -> dict:
    if (not isinstance(state, dict) or set(state) != {"schema", "rows"}
            or state["schema"] != 1 or not isinstance(state["rows"], list)
            or len(state["rows"]) > MAX_ROWS):
        raise ValueError("near-ready archive format/count invalid")
    seen = set()
    for row in state["rows"]:
        if not valid_event(row):
            raise ValueError("near-ready event invalid")
        key = (row["v"], row["s"], row["sd"], row["t"] // 300_000)
        if key in seen:
            raise ValueError("duplicate near-ready scan bucket")
        seen.add(key)
    return state


def encode(state: dict) -> bytes:
    validate(state)
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    if len(raw) > MAX_JSON:
        raise ValueError("near-ready JSON size invalid")
    data = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(data) > MAX_GZIP:
        raise ValueError("near-ready gzip size invalid")
    return data


def decode(data: bytes) -> dict:
    if len(data) > MAX_GZIP:
        raise ValueError("near-ready gzip size invalid")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise ValueError("near-ready decompressed size invalid")
        return validate(json.loads(raw.decode("utf-8")))
    except (ValueError, OSError, TypeError, UnicodeError):
        raise ValueError("near-ready archive unreadable") from None


def merge(existing: dict, incoming: list[dict], now: datetime) -> tuple[dict, int]:
    validate(existing)
    if now.tzinfo is None:
        raise ValueError("UTC timestamp required")
    today = now.astimezone(timezone.utc).date()
    rows = {(r["v"], r["s"], r["sd"], r["t"] // 300_000): r for r in existing["rows"]}
    added = 0
    for row in incoming:
        if (not valid_event(row) or row["t"] > int(now.timestamp() * 1000) + 5000
                or datetime.fromtimestamp(row["t"] / 1000, timezone.utc).date() != today):
            raise ValueError("invalid or wrong-day near-ready event")
        key = (row["v"], row["s"], row["sd"], row["t"] // 300_000)
        if key not in rows:
            rows[key] = row
            added += 1
    result = {"schema": 1, "rows": sorted(rows.values(), key=lambda r: (r["t"], r["v"], r["s"], r["sd"]))}
    validate(result)
    return result, added


class GitHubNearReadyStore(GitHubStateStore):
    def load(self, day: date) -> dict:
        self.day = day
        self.exists = self._request("GET", "/git/ref/heads/" + BRANCH,
                                    missing_ok=True) is not None
        if not self.exists:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        data = self._request("GET", "/contents/" + quote(day_path(day), safe="/") +
                             "?ref=" + BRANCH, missing_ok=True)
        if data is None:
            self.file_sha, self.current_blob = None, None
            return empty_history()
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            raise DeliveryError("near-ready archive API format invalid")
        try:
            raw = base64.b64decode(data["content"])
            state = decode(raw)
            if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != day
                   for r in state["rows"]):
                raise ValueError("near-ready UTC date mismatch")
        except (ValueError, TypeError):
            raise DeliveryError("near-ready archive unreadable; refusing overwrite") from None
        self.file_sha, self.current_blob = data.get("sha"), raw
        return state

    def save(self, state: dict) -> bool:
        if not hasattr(self, "day"):
            raise ValueError("load(day) required before save")
        validate(state)
        if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != self.day
               for r in state["rows"]):
            raise ValueError("near-ready cannot mix days")
        raw = encode(state)
        if raw == self.current_blob:
            return False
        if not self.exists:
            self._request("POST", "/git/refs", {"ref": "refs/heads/" + BRANCH,
                                                 "sha": self.default_sha})
            self.exists = True
        payload = {"message": "chore(orbit): near-ready research evidence [skip ci]",
                   "content": base64.b64encode(raw).decode("ascii"), "branch": BRANCH}
        if self.file_sha:
            payload["sha"] = self.file_sha
        result = self._request("PUT", "/contents/" + quote(day_path(self.day), safe="/"), payload)
        if not isinstance(result.get("content"), dict) or not result["content"].get("sha"):
            raise DeliveryError("near-ready archive write not acknowledged")
        self.file_sha, self.current_blob = result["content"]["sha"], raw
        return True


def fetch_public(days: int = 7, repository: str | None = None) -> dict:
    repository = repository or os.getenv("ORBIT_VALIDATION_REPOSITORY", DEFAULT_REPO)
    if days not in (1, 7, 30) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid near-ready history selection")
    today = datetime.now(timezone.utc).date()

    def read(day: date):
        url = f"https://raw.githubusercontent.com/{repository}/{BRANCH}/{day_path(day)}"
        try:
            with urlopen(Request(url, headers={"User-Agent": "OrbitNearReady/5.9.1"}),
                         timeout=12) as response:
                raw = response.read(MAX_GZIP + 1)
            rows = decode(raw)["rows"]
            if any(datetime.fromtimestamp(r["t"] / 1000, timezone.utc).date() != day
                   for r in rows):
                raise ValueError("near-ready dates mismatch")
            return rows
        except HTTPError as exc:
            if exc.code == 404:
                return []
            raise ValueError(f"near-ready archive HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("ยังโหลดประวัติ Near Ready จาก GitHub ไม่ได้") from None

    with ThreadPoolExecutor(max_workers=5) as pool:
        chunks = list(pool.map(read, [today - timedelta(days=i) for i in range(days)]))
    rows = sorted((r for chunk in chunks for r in chunk), key=lambda x: (x["t"], x["v"], x["s"]))
    return {"schema": 1, "rows": rows}
