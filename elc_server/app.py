#!/usr/bin/env python3
"""
Local Earth-Life Consortium–compatible API.

Composites Paleobiology Database (PBDB), Neotoma Paleoecology Database,
Macrostrat stratigraphic units, (optionally) Mindat mineral data, and
ePANDDA (PBDB + iDigBio) into a unified JSON response shaped like the
original ELC API (https://github.com/EarthLifeConsortium/elc_api).

Mindat requires MINDAT_API_KEY in key.env or .env (see .env.example).
Mindat query patterns follow https://github.com/ChuBL/How-to-Use-Mindat-API

ePANDDA docs: https://epandda.org/documentation_2.html
When api.epandda.org is unreachable, /epandda composes PBDB + iDigBio locally.

Macrostrat docs: https://macrostrat.org/api

Run:
    python -m elc_server.app
    # → http://127.0.0.1:8008/api_v1/

Endpoints:
    GET /api_v1/occ        fossil occurrences (+ Mindat / ePANDDA / Macrostrat via run=)
    GET /api_v1/tax        taxonomy
    GET /api_v1/loc        locales / collections (+ Mindat / Macrostrat)
    GET /api_v1/minerals   Mindat geomaterials search
    GET /api_v1/epandda    ePANDDA-shaped PBDB + iDigBio correlated results
    GET /api_v1/macrostrat Macrostrat units at lat/lng
    GET /api_v1/misc/timebound   resolve geologic age bounds via PBDB
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request

from . import adapters
from .env import load_dotenv, mindat_configured, mindat_enabled, mindat_key_status

load_dotenv()

app = Flask(__name__)

LICENSE = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0)"
DEFAULT_LIMIT = 500
DEFAULT_AGEUNITS = "ma"
# On-disk output from the recreated API (request log + last payload snapshot)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
REQUEST_LOG = os.path.join(DATA_DIR, "requests.log")
LAST_OCC_FILE = os.path.join(DATA_DIR, "last_occurrences.json")


@app.after_request
def add_cors_headers(response):
    """Allow browser clients (e.g. a static site) to call this API."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def public_base_url() -> str:
    """Prefer Render's public URL; otherwise derive from the incoming request."""
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")
    return request.url_root.rstrip("/")


def _truthy(val: str | None, default: bool = True) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y"}


def _run_list(run: str | None, *, default: list[str] | None = None) -> list[str]:
    """
    Parse run=… into backend names.
    default: used when run is omitted (fossil endpoints → neotoma+pbdb).
    run=all → neotoma, pbdb, epandda, macrostrat, and mindat (if a key is configured).
    """
    if not run:
        return list(default or ["neotoma", "pbdb"])
    if run.strip().lower() == "all":
        dbs = ["neotoma", "pbdb", "epandda", "macrostrat"]
        if mindat_configured():
            dbs.append("mindat")
        return dbs
    return [x.strip().lower() for x in run.split(",") if x.strip()]


def _parse_lat_lng() -> tuple[float | None, float | None]:
    lat_raw = request.args.get("lat")
    lng_raw = request.args.get("lng") or request.args.get("lon")
    if lat_raw is None or lng_raw is None:
        return None, None
    try:
        return float(lat_raw), float(lng_raw)
    except (TypeError, ValueError):
        return None, None


def _base_meta(ageunits: str, coordtype: str, includelower: bool) -> dict[str, Any]:
    return {
        "license": LICENSE,
        "retrieval_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source": f"{public_base_url()} (ELC-compatible API)",
        "age_units": ageunits,
        "coordinates": coordtype,
        "subtaxa_included": includelower,
    }


def append_request_log(endpoint: str, params: dict[str, Any], record_count: int) -> None:
    """Append one line describing this API call to a local log file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"{stamp} | {endpoint} | records={record_count} | params={params}\n"
    with open(REQUEST_LOG, "a", encoding="utf-8") as fh:
        fh.write(line)


def save_last_occurrences(payload: dict[str, Any]) -> None:
    """Write the latest /occ JSON payload to disk for inspection/reuse."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_OCC_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


@app.get("/")
@app.get("/api_v1/")
@app.get("/api_v1")
def index():
    backends = ["pbdb", "neotoma", "epandda", "macrostrat"]
    if mindat_configured():
        backends.append("mindat")
    return jsonify(
        {
            "name": "Local Earth-Life Consortium compatible API",
            "inspired_by": "https://github.com/EarthLifeConsortium/elc_api",
            "backends": backends,
            "mindat_enabled": mindat_enabled(),
            "mindat_configured": mindat_configured(),
            **mindat_key_status(),
            "endpoints": {
                "occurrences": "/api_v1/occ?taxon=Canis+dirus&limit=50",
                "taxonomy": "/api_v1/tax?taxon=Canis+dirus",
                "locales": "/api_v1/loc?taxon=Canis+dirus&limit=50",
                "minerals": "/api_v1/minerals?name=quartz&limit=20",
                "mindat_localities": "/api_v1/loc?taxon=quartz&run=mindat&limit=20",
                "epandda": "/api_v1/epandda?terms=hadrosaurus&limit=25",
                "epandda_via_occ": "/api_v1/occ?taxon=hadrosaurus&run=epandda&limit=25",
                "macrostrat": "/api_v1/macrostrat?lat=43.07&lng=-89.4&limit=20",
                "macrostrat_via_loc": "/api_v1/loc?lat=43.07&lng=-89.4&run=macrostrat",
                "timebound": "/api_v1/misc/timebound?agerange=pleistocene",
            },
        }
    )


@app.get("/api_v1/occ")
def occurrences():
    taxon = request.args.get("taxon")
    run_raw = request.args.get("run")
    lat, lng = _parse_lat_lng()
    point_macro = lat is not None and lng is not None and not taxon
    if point_macro and not run_raw:
        dbs = ["macrostrat"]
    else:
        dbs = _run_list(run_raw)

    if not taxon and "macrostrat" not in dbs:
        return jsonify(
            {
                "type": "about:blank",
                "title": "Bad Request",
                "detail": "Parameter required: taxon (or lat+lng with run=macrostrat)",
                "status": 400,
            }
        ), 400
    if not taxon and (lat is None or lng is None):
        return jsonify(
            {
                "type": "about:blank",
                "title": "Bad Request",
                "detail": "Parameter required: taxon (or lat+lng with run=macrostrat)",
                "status": 400,
            }
        ), 400

    ageunits = (request.args.get("ageunits") or DEFAULT_AGEUNITS).lower()
    if ageunits not in {"ma", "ka", "ybp"}:
        return jsonify({"detail": "ageunits must be ma|ka|ybp", "status": 400}), 400

    includelower = _truthy(request.args.get("includelower"), True)
    coordtype = (request.args.get("coordtype") or "modern").lower()
    limit = abs(int(request.args.get("limit") or DEFAULT_LIMIT))
    show = (request.args.get("show") or "all").lower()
    agerange = request.args.get("agerange")

    records: list[dict[str, Any]] = []
    meta = _base_meta(ageunits, coordtype, includelower)
    errors: dict[str, str] = {}

    if "pbdb" in dbs and taxon:
        try:
            rows, m = adapters.fetch_pbdb_occurrences(
                taxon,
                includelower=includelower,
                limit=limit,
                ageunits=ageunits,
                agerange=agerange,
            )
            records.extend(rows)
            meta["pbdb"] = m
        except Exception as exc:  # noqa: BLE001 — surface upstream errors in metadata
            errors["pbdb"] = str(exc)
            meta["pbdb"] = {"record_count": 0, "error": str(exc)}

    if "neotoma" in dbs and taxon:
        try:
            rows, m = adapters.fetch_neotoma_occurrences(
                taxon,
                includelower=includelower,
                limit=limit,
                ageunits=ageunits,
                agerange=agerange,
            )
            records.extend(rows)
            meta["neotoma"] = m
        except Exception as exc:  # noqa: BLE001
            errors["neotoma"] = str(exc)
            meta["neotoma"] = {"record_count": 0, "error": str(exc)}

    if "mindat" in dbs and taxon:
        if not mindat_configured():
            meta["mindat"] = {
                "record_count": 0,
                "disabled": True,
                "note": "Mindat inactive — set MINDAT_ENABLED=true in key.env when ready",
            }
        else:
            try:
                rows, m = adapters.fetch_mindat_occurrences(taxon, limit=limit)
                records.extend(rows)
                meta["mindat"] = m
            except Exception as exc:  # noqa: BLE001
                errors["mindat"] = str(exc)
                meta["mindat"] = {"record_count": 0, "error": str(exc)}

    if "epandda" in dbs and taxon:
        try:
            rows, m = adapters.fetch_epandda_occurrences(
                taxon, limit=limit, ageunits=ageunits
            )
            records.extend(rows)
            meta["epandda"] = m
        except Exception as exc:  # noqa: BLE001
            errors["epandda"] = str(exc)
            meta["epandda"] = {"record_count": 0, "error": str(exc)}

    if "macrostrat" in dbs:
        if lat is None or lng is None:
            meta["macrostrat"] = {
                "record_count": 0,
                "note": "Provide lat and lng (or lon) to query Macrostrat units",
            }
        else:
            try:
                rows, m = adapters.fetch_macrostrat_occurrences(
                    lat, lng, limit=limit, ageunits=ageunits
                )
                records.extend(rows)
                meta["macrostrat"] = m
            except Exception as exc:  # noqa: BLE001
                errors["macrostrat"] = str(exc)
                meta["macrostrat"] = {"record_count": 0, "error": str(exc)}

    if errors:
        meta["errors"] = errors

    append_request_log(
        "/api_v1/occ",
        {
            "taxon": taxon,
            "ageunits": ageunits,
            "limit": limit,
            "run": dbs,
            "agerange": agerange,
            "lat": lat,
            "lng": lng,
        },
        len(records),
    )

    if show == "poll":
        return jsonify(meta)
    if show == "idx":
        return jsonify([r.get("occ_id") for r in records if r.get("occ_id")])

    payload = {"metadata": meta, "records": records}
    save_last_occurrences(payload)
    return jsonify(payload)


@app.get("/api_v1/tax")
def taxonomy():
    taxon = request.args.get("taxon")
    if not taxon:
        return jsonify({"detail": "Parameter required: taxon", "status": 400}), 400

    includelower = _truthy(request.args.get("includelower"), False)
    limit = abs(int(request.args.get("limit") or DEFAULT_LIMIT))
    show = (request.args.get("show") or "all").lower()
    dbs = _run_list(request.args.get("run"))

    records: list[dict[str, Any]] = []
    meta = _base_meta(DEFAULT_AGEUNITS, "modern", includelower)

    if "pbdb" in dbs:
        try:
            rows, m = adapters.fetch_pbdb_taxonomy(taxon, includelower=includelower, limit=limit)
            records.extend(rows)
            meta["pbdb"] = m
        except Exception as exc:  # noqa: BLE001
            meta["pbdb"] = {"record_count": 0, "error": str(exc)}

    if "neotoma" in dbs:
        try:
            rows, m = adapters.fetch_neotoma_taxonomy(
                taxon, includelower=includelower, limit=limit
            )
            records.extend(rows)
            meta["neotoma"] = m
        except Exception as exc:  # noqa: BLE001
            meta["neotoma"] = {"record_count": 0, "error": str(exc)}

    if show == "poll":
        return jsonify(meta)
    return jsonify(metadata=meta, records=records)


@app.get("/api_v1/loc")
def locales():
    taxon = request.args.get("taxon")
    ageunits = (request.args.get("ageunits") or DEFAULT_AGEUNITS).lower()
    limit = abs(int(request.args.get("limit") or DEFAULT_LIMIT))
    agerange = request.args.get("agerange")
    run_raw = request.args.get("run")
    lat, lng = _parse_lat_lng()
    show = (request.args.get("show") or "all").lower()

    point_only = lat is not None and lng is not None and not taxon and not agerange
    if not taxon and not agerange and not point_only:
        return jsonify(
            {
                "detail": "Provide taxon, agerange, and/or lat+lng (for Macrostrat)",
                "status": 400,
            }
        ), 400

    # Point queries without an explicit run= default to Macrostrat only
    if point_only and not run_raw:
        dbs = ["macrostrat"]
    else:
        dbs = _run_list(run_raw)

    records: list[dict[str, Any]] = []
    meta = _base_meta(ageunits, "modern", True)

    if "pbdb" in dbs and (taxon or agerange):
        try:
            rows, m = adapters.fetch_pbdb_locales(
                taxon, limit=limit, ageunits=ageunits, agerange=agerange
            )
            records.extend(rows)
            meta["pbdb"] = m
        except Exception as exc:  # noqa: BLE001
            meta["pbdb"] = {"record_count": 0, "error": str(exc)}

    if "neotoma" in dbs and taxon:
        try:
            rows, m = adapters.fetch_neotoma_locales(taxon, limit=limit, ageunits=ageunits)
            records.extend(rows)
            meta["neotoma"] = m
        except Exception as exc:  # noqa: BLE001
            meta["neotoma"] = {"record_count": 0, "error": str(exc)}

    if "mindat" in dbs and taxon:
        if not mindat_configured():
            meta["mindat"] = {
                "record_count": 0,
                "disabled": True,
                "note": "Mindat inactive — set MINDAT_ENABLED=true in key.env when ready",
            }
        else:
            try:
                rows, m = adapters.fetch_mindat_localities(taxon, limit=limit)
                records.extend(rows)
                meta["mindat"] = m
            except Exception as exc:  # noqa: BLE001
                meta["mindat"] = {"record_count": 0, "error": str(exc)}

    if "macrostrat" in dbs:
        if lat is None or lng is None:
            meta["macrostrat"] = {
                "record_count": 0,
                "note": "Provide lat and lng (or lon) to query Macrostrat units",
            }
        else:
            try:
                rows, m = adapters.fetch_macrostrat_locales(
                    lat, lng, limit=limit, ageunits=ageunits
                )
                records.extend(rows)
                meta["macrostrat"] = m
            except Exception as exc:  # noqa: BLE001
                meta["macrostrat"] = {"record_count": 0, "error": str(exc)}

    if show == "poll":
        return jsonify(meta)
    return jsonify(metadata=meta, records=records)


@app.get("/api_v1/macrostrat")
def macrostrat():
    """
    Macrostrat stratigraphic units at a lat/lng.
    Docs: https://macrostrat.org/api
    """
    lat, lng = _parse_lat_lng()
    if lat is None or lng is None:
        return jsonify(
            {
                "detail": "Parameters required: lat and lng (or lon)",
                "status": 400,
                "example": "/api_v1/macrostrat?lat=43.07&lng=-89.4&limit=20",
                "docs": "https://macrostrat.org/api",
            }
        ), 400

    ageunits = (request.args.get("ageunits") or DEFAULT_AGEUNITS).lower()
    if ageunits not in {"ma", "ka", "ybp"}:
        return jsonify({"detail": "ageunits must be ma|ka|ybp", "status": 400}), 400
    limit = abs(int(request.args.get("limit") or DEFAULT_LIMIT))

    try:
        records, m = adapters.fetch_macrostrat_units(
            lat, lng, limit=limit, ageunits=ageunits
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"detail": str(exc), "status": 502}), 502

    meta = _base_meta(ageunits, "modern", False)
    meta["macrostrat"] = m
    append_request_log(
        "/api_v1/macrostrat",
        {"lat": lat, "lng": lng, "limit": limit, "ageunits": ageunits},
        len(records),
    )
    return jsonify(metadata=meta, records=records)


@app.get("/api_v1/epandda")
def epandda():
    """
    ePANDDA-compatible correlated PBDB + iDigBio results.
    Docs: https://epandda.org/documentation_2.html
    Primary param: terms= (e.g. hadrosaurus or genus:hadrosaurus|country:canada)
    """
    terms = request.args.get("terms") or request.args.get("taxon")
    if not terms:
        return jsonify(
            {
                "detail": "Parameter required: terms (e.g. hadrosaurus or genus:hadrosaurus)",
                "status": 400,
                "docs": "https://epandda.org/documentation_2.html",
            }
        ), 400

    limit = abs(int(request.args.get("limit") or 25))
    return_media = _truthy(request.args.get("returnMedia"), False)
    try:
        payload, meta = adapters.fetch_epandda_raw(
            terms,
            limit=limit,
            return_media=return_media,
            chrono_match_level=request.args.get("chronoMatchLevel"),
            taxon_match_level=request.args.get("taxonMatchLevel"),
            locality_match_level=request.args.get("localityMatchLevel"),
            match_on=request.args.get("matchOn"),
            geo_point_fields=request.args.get("geoPointFields"),
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"detail": str(exc), "status": 502}), 502

    append_request_log(
        "/api_v1/epandda",
        {"terms": terms, "limit": limit, "mode": meta.get("mode")},
        len(payload.get("results") or []),
    )
    # Attach local metadata without breaking ePANDDA response shape
    out = dict(payload)
    out["_elc_meta"] = meta
    return jsonify(out)


@app.get("/api_v1/minerals")
def minerals():
    """Mindat geomaterials search (requires MINDAT_API_KEY)."""
    name = request.args.get("name") or request.args.get("mineral")
    if not name:
        return jsonify({"detail": "Parameter required: name", "status": 400}), 400
    if not mindat_configured():
        if not mindat_enabled():
            detail = "Mindat is disabled (MINDAT_ENABLED=false)."
            hint = "Set MINDAT_ENABLED=true in the Render environment (or key.env locally)."
        else:
            detail = "Mindat is enabled but MINDAT_API_KEY is missing."
            hint = (
                "In Render → Environment, add secret MINDAT_API_KEY with your Mindat token, "
                "then redeploy. Locally: put MINDAT_API_KEY=… in key.env."
            )
        return jsonify(
            {
                "detail": detail,
                "status": 503,
                "mindat_enabled": mindat_enabled(),
                "mindat_configured": False,
                "hint": hint,
            }
        ), 503

    limit = abs(int(request.args.get("limit") or 50))
    try:
        records, m = adapters.fetch_mindat_minerals(name, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"detail": str(exc), "status": 502}), 502

    meta = _base_meta(DEFAULT_AGEUNITS, "modern", False)
    meta["mindat"] = m
    append_request_log("/api_v1/minerals", {"name": name, "limit": limit}, len(records))
    return jsonify(metadata=meta, records=records)


@app.get("/api_v1/misc/timebound")
def timebound():
    """Resolve a named geologic age (or numeric pair) via PBDB intervals."""
    agerange = request.args.get("agerange")
    ageunits = (request.args.get("ageunits") or DEFAULT_AGEUNITS).lower()
    if not agerange:
        return jsonify({"detail": "Parameter required: agerange", "status": 400}), 400

    parts = [p.strip() for p in agerange.split(",")]
    bounds = []
    for part in parts:
        if part[:1].isalpha():
            data, _ = adapters._get(  # noqa: SLF001 — shared HTTP helper
                adapters.PBDB_BASE + "intervals/single.json", {"name": part}
            )
            rec = (data.get("records") or [None])[0]
            if not rec:
                return jsonify({"detail": f"Unknown interval: {part}", "status": 404}), 404
            bounds.append((float(rec["eag"]), float(rec["lag"]), rec.get("nam") or part))
        else:
            val = float(part)
            # Interpret numeric age in requested units → Ma
            scale = {"ma": 1.0, "ka": 0.001, "ybp": 1e-6}[ageunits]
            ma = val * scale
            bounds.append((ma, ma, None))

    older = max(b[0] for b in bounds)
    younger = min(b[1] for b in bounds)
    # Convert Ma → requested units for the response
    out_scale = {"ma": 1.0, "ka": 1000.0, "ybp": 1_000_000.0}[ageunits]
    return jsonify(
        {
            "agerange": agerange,
            "ageunits": ageunits,
            "max_age": older * out_scale,
            "min_age": younger * out_scale,
            "resolved": [{"name": b[2], "eag_ma": b[0], "lag_ma": b[1]} for b in bounds],
        }
    )


def main() -> None:
    # Local: default 8008. On Render, use gunicorn (see Procfile / render.yaml).
    port = int(os.environ.get("PORT", "8008"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"ELC-compatible API → http://{host}:{port}/api_v1/")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
