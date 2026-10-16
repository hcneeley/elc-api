"""Age-unit conversion helpers (same scaling idea as original ELC)."""

from __future__ import annotations

UNIT = {"ybp": 1.0, "ka": 1_000.0, "ma": 1_000_000.0}
NATIVE = {"neotoma": "ybp", "pbdb": "ma"}


def age_scaler(ageunits: str, db: str) -> float:
    """
    Divide a database-native age by this factor to get ages in `ageunits`.

    PBDB stores Ma; Neotoma stores years before present (ybp).
    """
    elc = UNIT[ageunits.lower()]
    native = UNIT[NATIVE[db]]
    return elc / native


def scale_age(value, ageunits: str, db: str):
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0:
        return None
    return round(num / age_scaler(ageunits, db), 5)
