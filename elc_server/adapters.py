"""Fetch + normalize records from PBDB, Neotoma, and Mindat into ELC-shaped objects."""

from __future__ import annotations

import json
from time import time
from typing import Any
from urllib.parse import urlencode

import requests

from .ages import scale_age
from .env import mindat_api_key

PBDB_BASE = "https://paleobiodb.org/data1.2/"
NEOTOMA_BASE = "https://api.neotomadb.org/v2.0/data/"
MINDAT_BASE = "https://api.mindat.org/v1/"
TIMEOUT = 60


def _get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, str]:
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    full = resp.url
    resp.raise_for_status()
    return resp.json(), full


def _mindat_headers() -> dict[str, str]:
    key = mindat_api_key()
    if not key:
        raise ValueError(
            "Mindat API key not configured. Create a local .env with MINDAT_API_KEY=..."
        )
    return {"Authorization": f"Token {key}", "Accept": "application/json"}


def _parse_geojson_point(location: str | dict | None) -> tuple[float | None, float | None]:
    if not location:
        return None, None
    loc = json.loads(location) if isinstance(location, str) else location
    coords = loc.get("coordinates")
    if not coords:
        return None, None
    typ = (loc.get("type") or "").lower()
    if typ == "point":
        lon, lat = coords[0], coords[1]
        return float(lat), float(lon)
    # Polygon / MultiPolygon — take first vertex
    try:
        lon, lat = coords[0][0][0], coords[0][0][1]
        return float(lat), float(lon)
    except (IndexError, TypeError, ValueError):
        return None, None


# ---------------------------------------------------------------------------
# Occurrences
# ---------------------------------------------------------------------------

def fetch_pbdb_occurrences(
    taxon: str,
    *,
    includelower: bool,
    limit: int,
    ageunits: str,
    agerange: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    t0 = time()
    params: dict[str, Any] = {
        "show": "methods,coords,paleoloc",
        "limit": limit,
    }
    if includelower:
        params["base_name"] = taxon
    else:
        params["taxon_name"] = taxon

    if agerange:
        _apply_pbdb_agerange(params, agerange, ageunits)

    data, subquery = _get(PBDB_BASE + "occs/list.json", params)
    records: list[dict[str, Any]] = []
    for rec in data.get("records", []):
        oid = rec.get("oid") or "occ:0"
        tid = rec.get("tid") or "txn:0"
        cid = rec.get("cid") or "col:0"
        rid = rec.get("rid") or "ref:0"
        records.append(
            {
                "db": "pbdb",
                "occ_id": f"pbdb:{oid}",
                "taxon": rec.get("tna"),
                "taxon_id": f"pbdb:{tid}",
                "max_age": scale_age(rec.get("eag"), ageunits, "pbdb"),
                "min_age": scale_age(rec.get("lag"), ageunits, "pbdb"),
                "source": f"pbdb:{rid}",
                "data_type": rec.get("cct") or "general faunal/floral",
                "locale_id": f"pbdb:{cid}",
                "lat": _f(rec.get("lat")),
                "lon": _f(rec.get("lng")),
                "elevation": None,
            }
        )
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


def _resolve_neotoma_taxon_ids(taxon: str, includelower: bool) -> list[int]:
    """
    Neotoma's occurrences endpoint currently ignores `taxonname` (returns
    unrelated taxa). Resolve name → taxonid(s) via /taxa first.
    """
    params: dict[str, Any] = {"taxonname": taxon}
    if includelower:
        params["lower"] = "true"
    data, _ = _get(NEOTOMA_BASE + "taxa", params)
    ids: list[int] = []
    for rec in data.get("data") or []:
        tid = rec.get("taxonid")
        if tid is not None:
            ids.append(int(tid))
    return ids


def fetch_neotoma_occurrences(
    taxon: str,
    *,
    includelower: bool,
    limit: int,
    ageunits: str,
    agerange: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    t0 = time()
    taxon_ids = _resolve_neotoma_taxon_ids(taxon, includelower)
    if not taxon_ids:
        return [], {
            "subquery": None,
            "response_time": round(time() - t0, 3),
            "record_count": 0,
            "note": f"No Neotoma taxon match for {taxon!r}",
        }

    # Query each taxon id (Neotoma accepts a single taxonid)
    all_raw: list[dict[str, Any]] = []
    subqueries: list[str] = []
    remaining = limit
    for tid in taxon_ids:
        if remaining <= 0:
            break
        params: dict[str, Any] = {"taxonid": tid, "limit": remaining}
        if agerange:
            _apply_neotoma_agerange(params, agerange, ageunits)
        data, subquery = _get(NEOTOMA_BASE + "occurrences", params)
        subqueries.append(subquery)
        chunk = data.get("data") or []
        all_raw.extend(chunk)
        remaining = limit - len(all_raw)

    records: list[dict[str, Any]] = []
    for rec in all_raw[:limit]:
        sample = rec.get("sample") or {}
        age = rec.get("age") or {}
        site = rec.get("site") or {}
        lat, lon = _parse_geojson_point(site.get("location"))
        old = age.get("ageolder") if age.get("ageolder") is not None else age.get("age")
        yng = age.get("ageyounger") if age.get("ageyounger") is not None else age.get("age")
        dsid = site.get("datasetid")
        records.append(
            {
                "db": "neotoma",
                "occ_id": f"neot:occ:{rec.get('occid') or 0}",
                "taxon": sample.get("taxonname"),
                "taxon_id": f"neot:txn:{sample.get('taxonid') or 0}",
                "max_age": scale_age(old, ageunits, "neotoma"),
                "min_age": scale_age(yng, ageunits, "neotoma"),
                "source": site.get("database"),
                "data_type": site.get("datasettype"),
                "locale_id": f"neot:dst:{dsid}" if dsid is not None else None,
                "lat": lat,
                "lon": lon,
                "elevation": site.get("altitude"),
            }
        )

    meta = {
        "subquery": subqueries[0] if len(subqueries) == 1 else subqueries,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

def fetch_pbdb_taxonomy(taxon: str, *, includelower: bool, limit: int) -> tuple[list[dict], dict]:
    t0 = time()
    params: dict[str, Any] = {"show": "attr", "limit": limit}
    if includelower:
        params.update(name=taxon, rel="all_children")
    else:
        params["name"] = taxon
    data, subquery = _get(PBDB_BASE + "taxa/list.json", params)
    records = []
    for rec in data.get("records", []):
        oid = rec.get("oid") or "txn:0"
        par = rec.get("par") or "txn:0"
        rid = rec.get("rid") or "ref:0"
        try:
            status = "extant" if bool(int(rec.get("ext"))) else "extinct"
        except (TypeError, ValueError):
            status = None
        records.append(
            {
                "db": "pbdb",
                "taxon_id": f"pbdb:{oid}",
                "taxon": rec.get("nam") or rec.get("acn"),
                "parent_id": f"pbdb:{par}",
                "status": status,
                "source": f"pbdb:{rid}",
                "attribution": rec.get("att"),
                "rank": None,
                "common_name": rec.get("nm2"),
                "occurrences_count": rec.get("noc"),
                "early_interval": rec.get("tei"),
                "late_interval": rec.get("tli"),
                "subtaxa_count": rec.get("siz"),
                "subtaxa_extant": rec.get("exs"),
                "ecological_group": None,
            }
        )
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


def fetch_neotoma_taxonomy(taxon: str, *, includelower: bool, limit: int) -> tuple[list[dict], dict]:
    t0 = time()
    params: dict[str, Any] = {"taxonname": taxon, "limit": limit}
    if includelower:
        params["lower"] = "true"
    data, subquery = _get(NEOTOMA_BASE + "taxa", params)
    records = []
    for rec in (data.get("data") or [])[:limit]:
        pub = rec.get("publicationid")
        parent = rec.get("highertaxonid")
        records.append(
            {
                "db": "neotoma",
                "taxon_id": f"neot:txn:{rec.get('taxonid')}" if rec.get("taxonid") else None,
                "taxon": rec.get("taxonname"),
                "parent_id": f"neot:txn:{parent}" if parent else None,
                "status": rec.get("status"),
                "source": f"neot:pub:{pub}" if pub else None,
                "attribution": rec.get("author"),
                "rank": None,
                "common_name": None,
                "occurrences_count": None,
                "ecological_group": rec.get("ecolgroup"),
            }
        )
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


# ---------------------------------------------------------------------------
# Locales (collections / datasets)
# ---------------------------------------------------------------------------

def fetch_pbdb_locales(
    taxon: str | None,
    *,
    limit: int,
    ageunits: str,
    agerange: str | None = None,
) -> tuple[list[dict], dict]:
    t0 = time()
    params: dict[str, Any] = {"show": "full", "limit": limit}
    if taxon:
        params["base_name"] = taxon
    if agerange:
        _apply_pbdb_agerange(params, agerange, ageunits)
    data, subquery = _get(PBDB_BASE + "colls/list.json", params)
    records = []
    for rec in data.get("records", []):
        oid = rec.get("oid") or "col:0"
        rid = rec.get("rid") or "ref:0"
        records.append(
            {
                "db": "pbdb",
                "locale_id": f"pbdb:{oid}",
                "doi": None,
                "source": f"pbdb:{rid}",
                "locale_name": rec.get("nam"),
                "data_type": rec.get("cct") or "general faunal/floral",
                "occurrences_count": rec.get("noc"),
                "site_id": None,
                "max_age": scale_age(rec.get("eag"), ageunits, "pbdb"),
                "min_age": scale_age(rec.get("lag"), ageunits, "pbdb"),
                "lat": _f(rec.get("lat")),
                "lon": _f(rec.get("lng")),
                "elevation": None,
            }
        )
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


def fetch_neotoma_locales(
    taxon: str | None,
    *,
    limit: int,
    ageunits: str,
) -> tuple[list[dict], dict]:
    """
    Neotoma locale analogue: unique datasets from occurrence hits for a taxon.
    (Original ELC used a custom datasets_elc route that is no longer public.)
    """
    t0 = time()
    if not taxon:
        return [], {
            "subquery": None,
            "response_time": 0,
            "record_count": 0,
            "note": "taxon required for Neotoma locales in this local API",
        }

    occs, occ_meta = fetch_neotoma_occurrences(
        taxon, includelower=True, limit=limit, ageunits=ageunits
    )
    seen: dict[str, dict] = {}
    for o in occs:
        lid = o.get("locale_id")
        if not lid or lid in seen:
            continue
        seen[lid] = {
            "db": "neotoma",
            "locale_id": lid,
            "doi": None,
            "source": o.get("source"),
            "locale_name": None,
            "data_type": o.get("data_type"),
            "occurrences_count": None,
            "site_id": None,
            "max_age": o.get("max_age"),
            "min_age": o.get("min_age"),
            "lat": o.get("lat"),
            "lon": o.get("lon"),
            "elevation": o.get("elevation"),
        }
    records = list(seen.values())
    meta = {
        "subquery": occ_meta.get("subquery"),
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


# ---------------------------------------------------------------------------
# Age-range helpers
# ---------------------------------------------------------------------------

def _f(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_numeric_agerange(agerange: str, ageunits: str) -> tuple[float, float] | None:
    """Return (older_ma, younger_ma) if agerange is numeric; else None."""
    parts = [p.strip() for p in agerange.split(",")]
    if len(parts) != 2:
        return None
    try:
        a, b = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    # Convert requested units → Ma for PBDB; keep as Ma pair
    scale = {"ma": 1.0, "ka": 0.001, "ybp": 1e-6}[ageunits.lower()]
    a_ma, b_ma = a * scale, b * scale
    older, younger = max(a_ma, b_ma), min(a_ma, b_ma)
    return older, younger


def _apply_pbdb_agerange(params: dict, agerange: str, ageunits: str) -> None:
    pair = _parse_numeric_agerange(agerange, ageunits)
    if pair:
        params["max_ma"], params["min_ma"] = pair
        return
    # Named geologic interval(s) — pass through to PBDB interval resolver via max/min
    # Fall back: treat single named age as interval name filter
    parts = [p.strip() for p in agerange.split(",")]
    if len(parts) == 1 and parts[0][0].isalpha():
        # Resolve via PBDB intervals
        try:
            data, _ = _get(PBDB_BASE + "intervals/single.json", {"name": parts[0]})
            rec = (data.get("records") or [None])[0]
            if rec:
                params["max_ma"] = rec.get("eag")
                params["min_ma"] = rec.get("lag")
        except requests.RequestException:
            pass


def _apply_neotoma_agerange(params: dict, agerange: str, ageunits: str) -> None:
    pair = _parse_numeric_agerange(agerange, ageunits)
    if not pair:
        return
    older_ma, younger_ma = pair
    # Neotoma wants ybp
    params["ageold"] = int(older_ma * 1_000_000)
    params["ageyoung"] = int(younger_ma * 1_000_000)


# ---------------------------------------------------------------------------
# Mindat (minerals / localities)
# Patterns follow https://github.com/ChuBL/How-to-Use-Mindat-API
# (geomaterials-search?q=…, lean fields=, localities via id__in=)
# ---------------------------------------------------------------------------

MINDAT_MINERAL_FIELDS = "id,name,mindat_formula,ima_formula,csystem,hmin,hmax,ima_status"
MINDAT_LOCALITY_FIELDS = "id,txt,latitude,longitude,country"


def _mindat_results(data: Any) -> list[dict[str, Any]]:
    """Normalize DRF-style and bare-list Mindat responses."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
        # Single-object retrieve sometimes returns the object itself
        if "id" in data and ("name" in data or "txt" in data):
            return [data]
    return []


def _mindat_get(path: str, params: dict[str, Any] | None = None) -> tuple[Any, str]:
    """GET Mindat with auth; retries once on 504/timeout with a leaner request."""
    headers = _mindat_headers()
    params = dict(params or {})
    params.setdefault("format", "json")
    url = MINDAT_BASE + path.lstrip("/")
    try:
        return _get(url, params=params, headers=headers)
    except requests.RequestException:
        # Retry with smaller page / explicit fields (OpenMindat tip for timeouts)
        lean = dict(params)
        if "page_size" in lean:
            lean["page_size"] = min(int(lean["page_size"]), 5)
        if "size" in lean:
            lean["size"] = min(int(lean["size"]), 5)
        lean.setdefault("fields", MINDAT_MINERAL_FIELDS)
        return _get(url, params=lean, headers=headers)


def _normalize_mineral(rec: dict[str, Any]) -> dict[str, Any]:
    mid = rec.get("id")
    return {
        "db": "mindat",
        "mineral_id": f"mindat:min:{mid}" if mid is not None else None,
        "name": rec.get("name") or rec.get("title"),
        "formula": rec.get("mindat_formula") or rec.get("ima_formula") or rec.get("formula"),
        "ima_status": rec.get("ima_status"),
        "elements": rec.get("elements") or rec.get("elements_inc"),
        "crystal_system": rec.get("csystem") or rec.get("crystal_system"),
        "hardness_min": rec.get("hmin"),
        "hardness_max": rec.get("hmax"),
        "locality_ids": rec.get("locality") or [],
        "mindat_url": f"https://www.mindat.org/min-{mid}.html" if mid is not None else None,
        "raw_entrytype": rec.get("entrytype_text") or rec.get("entrytype"),
    }


def fetch_mindat_minerals(
    name: str,
    *,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Search Mindat via /v1/geomaterials-search/?q=… (tutorial pattern).
    Falls back to /v1/minerals-ima/?q=… then geomaterials list filters.
    """
    t0 = time()
    subquery = None
    rows: list[dict[str, Any]] = []

    # 1) Homepage-style keyword search (ChuBL tutorial: GeomaterialSearchRetriever)
    try:
        data, subquery = _mindat_get(
            "geomaterials-search/",
            {"q": name, "size": min(limit, 50), "ima": 1},
        )
        rows = _mindat_results(data)
    except requests.RequestException:
        rows = []

    # 2) IMA list keyword search
    if not rows:
        try:
            data, subquery = _mindat_get(
                "minerals-ima/",
                {"q": name, "page": 1, "page_size": min(limit, 50)},
            )
            rows = _mindat_results(data)
        except requests.RequestException:
            rows = []

    # 3) Geomaterials list with lean fields + page=1
    if not rows:
        data, subquery = _mindat_get(
            "geomaterials/",
            {
                "q": name,
                "page": 1,
                "page_size": min(limit, 50),
                "fields": MINDAT_MINERAL_FIELDS,
            },
        )
        rows = _mindat_results(data)

    records = [_normalize_mineral(rec) for rec in rows[:limit]]
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
    }
    return records, meta


def fetch_mindat_localities(
    mineral: str,
    *,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Resolve localities for a mineral the tutorial way:
      geomaterial (expand=locality) → localities?id__in=…
    """
    t0 = time()
    minerals, min_meta = fetch_mindat_minerals(mineral, limit=5)
    if not minerals:
        return [], {
            "subquery": min_meta.get("subquery"),
            "response_time": round(time() - t0, 3),
            "record_count": 0,
            "note": f"No Mindat mineral match for {mineral!r}",
        }

    # Prefer the best name match; gather locality ids from expand=locality
    top = minerals[0]
    mid = (top.get("mineral_id") or "").split(":")[-1]
    loc_ids: list[int] = []
    subquery = min_meta.get("subquery")

    if mid:
        try:
            data, subquery = _mindat_get(
                f"geomaterials/{mid}/",
                {
                    "expand": "locality",
                    "fields": "id,name,locality",
                },
            )
            detail = _mindat_results(data)
            if detail:
                loc_ids = [int(x) for x in (detail[0].get("locality") or []) if str(x).isdigit()]
        except (requests.RequestException, ValueError, TypeError):
            loc_ids = [int(x) for x in (top.get("locality_ids") or []) if str(x).isdigit()]

    if not loc_ids:
        return [], {
            "subquery": subquery,
            "response_time": round(time() - t0, 3),
            "record_count": 0,
            "note": f"Mineral {top.get('name')!r} has no locality ids in Mindat response",
            "mineral": top,
        }

    loc_ids = loc_ids[:limit]
    data, subquery = _mindat_get(
        "localities/",
        {
            "id__in": ",".join(str(i) for i in loc_ids),
            "fields": MINDAT_LOCALITY_FIELDS,
            "page_size": min(limit, 100),
            "page": 1,
        },
    )

    records: list[dict[str, Any]] = []
    for rec in _mindat_results(data)[:limit]:
        lid = rec.get("id")
        lat = _f(rec.get("latitude"))
        lon = _f(rec.get("longitude"))
        # Mindat uses 0,0 for “no coordinates” (countries/districts)
        if lat == 0.0 and lon == 0.0:
            lat, lon = None, None
        records.append(
            {
                "db": "mindat",
                "locale_id": f"mindat:loc:{lid}" if lid is not None else None,
                "doi": None,
                "source": "mindat.org",
                "locale_name": rec.get("txt") or rec.get("name"),
                "data_type": "mineral locality",
                "occurrences_count": None,
                "site_id": None,
                "max_age": None,
                "min_age": None,
                "lat": lat,
                "lon": lon,
                "elevation": None,
                "country": rec.get("country"),
                "mineral": top.get("name"),
                "mindat_url": (
                    f"https://www.mindat.org/loc-{lid}.html" if lid is not None else None
                ),
            }
        )
    meta = {
        "subquery": subquery,
        "response_time": round(time() - t0, 3),
        "record_count": len(records),
        "mineral": top.get("name"),
    }
    return records, meta


def fetch_mindat_occurrences(
    mineral: str,
    *,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Map Mindat localities for a mineral into ELC-like occurrence records
    so they can be merged when run=mindat (or run includes mindat).
    """
    locales, meta = fetch_mindat_localities(mineral, limit=limit)
    records = []
    for loc in locales:
        records.append(
            {
                "db": "mindat",
                "occ_id": loc.get("locale_id"),
                "taxon": loc.get("mineral") or mineral,
                "taxon_id": None,
                "max_age": None,
                "min_age": None,
                "source": loc.get("source"),
                "data_type": loc.get("data_type"),
                "locale_id": loc.get("locale_id"),
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "elevation": loc.get("elevation"),
            }
        )
    meta = {**meta, "record_count": len(records)}
    return records, meta
