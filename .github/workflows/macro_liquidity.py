"""DefiLlama *market-wide* context from documented keyless public endpoints.

Stablecoin circulating amount and DeFi TVL are NOT exchange net deposits,
whale transactions, or precise proxies for dollars available to buy any coin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE = "https://api.llama.fi"
STABLE_BASE = "https://stablecoins.llama.fi"


@dataclass(frozen=True)
class MarketLiquidity:
    stablecoin_supply_usd: float | None
    stablecoin_change_7d_pct: float | None
    stablecoin_asof: datetime | None
    defi_tvl_usd: float | None
    defi_tvl_change_7d_pct: float | None
    tvl_asof: datetime | None
    source: str = "DefiLlama Free API: stablecoincharts/all + v2/historicalChainTvl"


def _number(value):
    if isinstance(value, dict):
        value = value.get("peggedUSD")
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) and n >= 0 else None


def _series(chart: object, key: str, now: datetime) -> tuple[float | None, float | None, datetime | None]:
    if not isinstance(chart, list):
        return None, None, None
    samples = []
    for item in chart:
        if not isinstance(item, dict):
            continue
        try:
            stamp = int(item["date"])
            asof = datetime.fromtimestamp(stamp, timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        value = _number(item.get(key))
        if value is not None and asof <= now:
            samples.append((asof, value))
    if not samples:
        return None, None, None
    samples.sort()
    asof, current = samples[-1]
    if (now - asof).total_seconds() > 3 * 86400:
        return None, None, asof  # stale: do not report an obsolete point as current
    target_ts = asof.timestamp() - 7 * 86400
    past = min(samples, key=lambda item: abs(item[0].timestamp() - target_ts))
    within_days = abs(past[0].timestamp() - target_ts) <= 2 * 86400
    change = ((current / past[1] - 1) * 100 if within_days and past[1] > 0 else None)
    return current, change, asof


def parse_market_liquidity(stablecoin_chart: object, tvl_chart: object, *, now: datetime) -> MarketLiquidity:
    if now.tzinfo is None:
        raise ValueError("เวลาแหล่งข้อมูลต้องมี timezone")
    # Field is the market value of USD-pegged stablecoins, not nominal units
    # of all currencies (EUR, JPY, etc.). Confirmed against live free response.
    stable, change_s, asof_s = _series(stablecoin_chart, "totalCirculatingUSD", now)
    tvl, change_t, asof_t = _series(tvl_chart, "tvl", now)
    return MarketLiquidity(stable, change_s, asof_s, tvl, change_t, asof_t)


def _public_json(path: str):
    try:
        base = STABLE_BASE if path.startswith("/stablecoin") else BASE
        req = Request(base + path, headers={"User-Agent": "OrbitPro/Final read-only"})
        with urlopen(req, timeout=15) as handle:
            return json.load(handle)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"DefiLlama ไม่พร้อม: {exc}") from exc


def fetch_market_liquidity() -> MarketLiquidity:
    """Keyless endpoints; no scrapers or privately authenticated datasets."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        stable_future = pool.submit(_public_json, "/stablecoincharts/all")
        tvl_future = pool.submit(_public_json, "/v2/historicalChainTvl")
        stable = stable_future.result()
        tvl = tvl_future.result()
    return parse_market_liquidity(stable, tvl, now=datetime.now(timezone.utc))
