#!/usr/bin/env python3
"""
Earth-Life Consortium (ELC) API script
--------------------------------------
Queries fossil occurrences for a taxon via a local ELC-compatible API
(composites Neotoma + PBDB), then:
  - prints a summary (counts by database, age span, geographic extent)
  - saves a curated CSV of selected fields
  - graphs a geographic scatter map and an age histogram

Local API (replacement for down earthlifeconsortium.org):
    python -m elc_server.app
    → http://127.0.0.1:8008/api_v1/

Original schema: https://github.com/EarthLifeConsortium/elc_api

Assignment checklist covered by this script:
  - data source: web service / API (requests.get to ELC-compatible /occ)
  - for loop: iterating records / databases when summarizing and saving
  - if statement: live API vs fallback, empty results, numeric checks
  - functions: fetch_occurrences, save_csv, plot_map_and_ages, and helpers
  - imports: csv, os, collections, matplotlib, requests, ...
  - write to file: curated CSV + map/age PNG under output/
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from typing import Any
from urllib.parse import urlencode

import matplotlib.pyplot as plt
import requests

# Prefer ELC_BASE env (set to your Render URL after deploy), else local server
# Example: export ELC_BASE=https://elc-api.onrender.com/api_v1
ELC_BASE = os.environ.get("ELC_BASE", "http://127.0.0.1:8008/api_v1")
TAXON = "canis dirus"
LIMIT = 500
AGE_UNITS = "ma"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

WAYBACK_FALLBACK = (
    "https://web.archive.org/web/20220404101244id_/"
    "http://earthlifeconsortium.org/api_v1/occ?taxon=canis+dirus"
)


def build_occ_url(taxon: str, limit: int, ageunits: str) -> str:
    params = {
        "taxon": taxon,
        "includelower": "true",
        "limit": str(limit),
        "ageunits": ageunits,
        "output": "json",
        "show": "all",
    }
    return f"{ELC_BASE}/occ?{urlencode(params)}"


def fetch_occurrences(taxon: str = TAXON) -> tuple[dict[str, Any], str]:
    """Return (payload, source_label). Tries local ELC server, then Wayback."""
    live_url = build_occ_url(taxon, LIMIT, AGE_UNITS)
    print(f"GET {live_url}")
    try:
        resp = requests.get(live_url, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        if "records" not in data:
            raise ValueError("Unexpected response shape (no 'records')")
        return data, f"local ELC-compatible API ({ELC_BASE})"
    except (requests.RequestException, ValueError) as exc:
        print(f"Local ELC unreachable ({exc.__class__.__name__}: {exc}).")
        print("Start it with:  python -m elc_server.app")
        print(f"Falling back to Wayback Machine snapshot…\nGET {WAYBACK_FALLBACK}")
        resp = requests.get(WAYBACK_FALLBACK, timeout=60)
        resp.raise_for_status()
        return resp.json(), "Wayback Machine archive of ELC /api_v1/occ"


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def database_of(record: dict[str, Any]) -> str:
    if record.get("db"):
        return str(record["db"]).lower()
    for key in ("occ_id", "locale_id", "taxon_id"):
        val = str(record.get(key) or "")
        if val.startswith("neot:"):
            return "neotoma"
        if val.startswith("pbdb:"):
            return "pbdb"
        if val.startswith("sead:"):
            return "sead"
    return "unknown"


def mean_age(record: dict[str, Any]) -> float | None:
    mx, mn = as_float(record.get("max_age")), as_float(record.get("min_age"))
    if mx is None and mn is None:
        return None
    if mx is None:
        return mn
    if mn is None:
        return mx
    return (mx + mn) / 2.0


def summarize(payload: dict[str, Any], source_label: str) -> None:
    meta = payload.get("metadata") or {}
    records = payload.get("records") or []
    db_counts = Counter(database_of(r) for r in records)
    ages = [a for r in records if (a := mean_age(r)) is not None]
    lats = [lat for r in records if (lat := as_float(r.get("lat"))) is not None]
    lons = [lon for r in records if (lon := as_float(r.get("lon"))) is not None]
    taxa = Counter(r.get("taxon") or "?" for r in records)

    print("\n=== Earth-Life Consortium occurrences ===")
    print(f"Data source: {source_label}")
    print(f"Taxon query: {TAXON!r}")
    print(f"Records returned: {len(records)}")
    if meta:
        print(f"Age units: {meta.get('age_units')} | coords: {meta.get('coordinates')}")
        for db in ("pbdb", "neotoma", "sead"):
            block = meta.get(db)
            if isinstance(block, dict):
                print(
                    f"  metadata[{db}]: {block.get('record_count')} records "
                    f"({block.get('response_time')} s)"
                )

    print("\nOccurrences by database:")
    for db, n in db_counts.most_common():
        print(f"  {db:12s}  {n}")

    print("\nTop taxon names in response:")
    for name, n in taxa.most_common(8):
        print(f"  {name:30s}  {n}")

    if ages:
        print(f"\nAge span (mean of max/min): {max(ages):.4f} → {min(ages):.4f} {AGE_UNITS}")
    if lats and lons:
        print(
            f"Geographic extent: lat [{min(lats):.2f}, {max(lats):.2f}], "
            f"lon [{min(lons):.2f}, {max(lons):.2f}]"
        )


def save_csv(records: list[dict[str, Any]], path: str) -> None:
    fields = [
        "occ_id",
        "taxon",
        "database",
        "lat",
        "lon",
        "max_age",
        "min_age",
        "mean_age",
        "elevation",
        "data_type",
        "locale_id",
        "source",
    ]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "occ_id": r.get("occ_id"),
                    "taxon": r.get("taxon"),
                    "database": database_of(r),
                    "lat": as_float(r.get("lat")),
                    "lon": as_float(r.get("lon")),
                    "max_age": as_float(r.get("max_age")),
                    "min_age": as_float(r.get("min_age")),
                    "mean_age": mean_age(r),
                    "elevation": as_float(r.get("elevation")),
                    "data_type": r.get("data_type"),
                    "locale_id": r.get("locale_id"),
                    "source": r.get("source"),
                }
            )
    print(f"\nSaved curated table → {path}")


def plot_map_and_ages(records: list[dict[str, Any]], path: str) -> None:
    by_db: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_db.setdefault(database_of(r), []).append(r)

    colors = {"neotoma": "#2a9d8f", "pbdb": "#e76f51", "sead": "#264653", "unknown": "#6c757d"}

    fig, (ax_map, ax_age) = plt.subplots(1, 2, figsize=(12, 5))

    for db, rows in by_db.items():
        pts = [(as_float(r.get("lon")), as_float(r.get("lat"))) for r in rows]
        pts = [(x, y) for x, y in pts if x is not None and y is not None]
        if pts:
            xs, ys = zip(*pts)
            ax_map.scatter(xs, ys, s=28, alpha=0.7, label=db, c=colors.get(db, "#333"))
    ax_map.set_xlabel("Longitude")
    ax_map.set_ylabel("Latitude")
    ax_map.set_title(f"Modern localities — {TAXON}")
    ax_map.legend(loc="best", fontsize=8)
    ax_map.grid(True, alpha=0.3)

    for db, rows in by_db.items():
        ages = [a for r in rows if (a := mean_age(r)) is not None]
        if ages:
            ax_age.hist(
                ages,
                bins=15,
                alpha=0.55,
                label=db,
                color=colors.get(db, "#333"),
                edgecolor="white",
            )
    ax_age.set_xlabel(f"Mean age ({AGE_UNITS})")
    ax_age.set_ylabel("Occurrence count")
    ax_age.set_title("Age distribution by database")
    ax_age.invert_xaxis()
    ax_age.legend(loc="best", fontsize=8)
    ax_age.grid(True, axis="y", alpha=0.3)

    fig.suptitle("ELC-compatible API — Canis dirus occurrences", fontsize=12)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved map + age chart → {path}")


def main() -> None:
    payload, source_label = fetch_occurrences(TAXON)
    records = payload.get("records") or []
    if not records:
        print("No occurrence records returned.")
        return

    summarize(payload, source_label)
    csv_path = os.path.join(OUTPUT_DIR, "elc_canis_dirus.csv")
    fig_path = os.path.join(OUTPUT_DIR, "elc_canis_dirus_map_ages.png")
    save_csv(records, csv_path)
    plot_map_and_ages(records, fig_path)


if __name__ == "__main__":
    main()
