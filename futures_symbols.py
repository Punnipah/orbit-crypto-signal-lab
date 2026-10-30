"""Safe display-symbol to exchange-contract matching for USDT perpetuals.

An exchange contract such as 1000PEPEUSDT is priced per 1,000 PEPE.
Its contract price must never be presented as a PEPE spot unit price.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FuturesPair:
    requested: str
    contract: str
    multiplier: int = 1

    @property
    def underlying(self) -> str:
        return self.requested.removesuffix("USDT")

    @property
    def label(self) -> str:
        return f"{self.contract} · {self.multiplier:,} {self.underlying} / contract"

    def unit_price(self, contract_price: float) -> float:
        return contract_price / self.multiplier


def resolve_futures_pair(requested: str, catalog: set[str]) -> FuturesPair:
    """Prefer an exact contract; otherwise resolve only unambiguous known multipliers.

    No fuzzy asset-name matching or arbitrary substring lookup is permitted.
    """
    if not isinstance(requested, str) or not re.fullmatch(r"[A-Z0-9]{2,20}USDT", requested):
        raise ValueError("Futures symbol ไม่ถูกต้อง")
    if requested in catalog:
        return FuturesPair(requested, requested)
    asset = requested.removesuffix("USDT")
    candidates = [(multiple, f"{multiple}{asset}USDT")
                  for multiple in (1000, 10000, 1000000)
                  if f"{multiple}{asset}USDT" in catalog]
    if len(candidates) != 1:
        raise ValueError(f"ไม่พบสัญญา Futures หรือมีหลายหน่วยที่ต้องเลือกเอง: {requested}")
    multiple, contract = candidates[0]
    return FuturesPair(requested, contract, multiple)
