"""Simple unit conversion: ``<number> <from> <to>`` (e.g. ``100 c f``).

Covers the conversions people actually type into a launcher.
"""
from __future__ import annotations

import math
import re

_CONVERSION_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+([A-Za-z]{1,5})\s+([A-Za-z]{1,5})\s*$")

# factor: value_in_base = value * factor
_FACTORS = {
    # length (base: meter)
    "m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001,
    "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "yd": 0.9144,
    # mass (base: gram)
    "g": 1.0, "kg": 1000.0, "mg": 0.001, "t": 1_000_000.0,
    "lb": 453.59237, "oz": 28.349523125,
    # volume (base: liter)
    "l": 1.0, "ml": 0.001, "cl": 0.01, "gal": 3.785411784,
    # data (base: megabyte)
    "kb": 0.001, "mb": 1.0, "gb": 1000.0, "tb": 1_000_000.0,
    # speed (base: m/s)
    "ms": 1.0, "kmh": 1.0 / 3.6, "mph": 0.44704,
    # time (base: second)
    "s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0,
}

# temperature handled separately (offset formulas), base: celsius
_TEMP_UNITS = {"c", "f", "k"}


def _to_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return (value - 32.0) * 5.0 / 9.0
    return value - 273.15


def _from_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return value * 9.0 / 5.0 + 32.0
    return value + 273.15


def _fmt(x: float) -> str:
    if math.isnan(x) or math.isinf(x):
        raise ValueError("not finite")
    if x != 0 and (abs(x) >= 1e15 or abs(x) < 1e-9):
        return f"{x:.6e}"
    r = round(x, 8)
    if r == int(r) and abs(r) < 1e15:
        return str(int(r))
    return f"{r:.8f}".rstrip("0").rstrip(".")


def try_convert(text: str) -> str | None:
    """Convert ``<number> <from> <to>``; return ``"result unit"`` or None."""
    m = _CONVERSION_RE.match(text or "")
    if not m:
        return None
    number = float(m.group(1))
    src, dst = m.group(2).lower(), m.group(3).lower()
    try:
        if src in _TEMP_UNITS and dst in _TEMP_UNITS:
            if src == dst:
                return None
            result = _from_celsius(_to_celsius(number, src), dst)
        elif src in _FACTORS and dst in _FACTORS:
            result = number * _FACTORS[src] / _FACTORS[dst]
        else:
            return None
    except (ValueError, ZeroDivisionError):
        return None
    return f"{_fmt(result)} {dst}"
