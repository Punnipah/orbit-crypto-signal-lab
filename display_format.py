"""Human-readable prices for markets with very different tick magnitudes.

Display rounding must never make a positive low-price asset look like zero.
These helpers only format values; trading and risk calculations keep floats.
"""

from __future__ import annotations

import math


def format_price(value: float) -> str:
    """Show up to six significant fractional digits without scientific notation.

    Values too small to fit within 16 decimal places use scientific notation
    explicitly, rather than rounding to zero.
    """
    if not math.isfinite(value):
        return "ไม่พร้อม"
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 10:
        return f"{value:,.2f}"
    if magnitude >= 1:
        formatted = f"{value:,.6f}"
    else:
        digits = max(6, 5 - math.floor(math.log10(magnitude)))
        if digits > 16:
            return f"{value:.6e}"
        formatted = f"{value:,.{digits}f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def format_signed_price(value: float) -> str:
    return ("+" if value > 0 else "") + format_price(value)
