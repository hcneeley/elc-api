#!/usr/bin/env python3
"""
Local Earth-Life Consortium–compatible API.

Composites Paleobiology Database (PBDB), Neotoma Paleoecology Database,
and (optionally) Mindat mineral data into a unified JSON response shaped
like the original ELC API (https://github.com/EarthLifeConsortium/elc_api).

Mindat requires MINDAT_API_KEY in key.env or .env (see .env.example).
Mindat query patterns follow https://github.com/ChuBL/How-to-Use-Mindat-API

Run:
    python -m elc_server.app
    # → http://127.0.0.1:8008/api_v1/

Endpoints:
    GET /api_v1/occ        fossil occurrences (+ Mindat localities if run includes mindat)
    GET /api_v1/tax        taxonomy
    GET /api_v1/loc        locales / collections (+ Mindat localities)
    GET /api_v1/minerals   Mindat geomaterials search
    GET /api_v1/misc/timebound   resolve geologic age bounds via PBDB
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request

from . import adapters
from .env import load_dotenv, mindat_configured, mindat_enabled

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
    run=all → neotoma, pbdb, and mindat (if a key is configured).
    """
    if not run:
        return list(default or ["neotoma", "pbdb"])
    if run.strip().lower() == "all":
        dbs = ["neotoma", "pbdb"]
        if mindat_configured():
            dbs.append("mindat")
        return dbs
    return [x.strip().lower() for x in run.split(",") if x.strip()]


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
    backends = ["pbdb", "neotoma"]
    if mindat_configured():
        backends.append("mindat")
    return jsonify(
        {
            "name": "Local Earth-Life Consortium compatible API",
            "inspired_by": "https://github.com/EarthLifeConsortium/elc_api",
            "backends": backends,
            "mindat_enabled": mindat_enabled(),
            "mindat_configured": mindat_configured(),
            "endpoints": {
                "occurrences": "/api_v1/occ?taxon=Canis+dirus&limit=50",
                "taxonomy": "/api_v1/tax?taxon=Canis+dirus",
                "locales": "/api_v1/loc?taxon=Canis+dirus&limit=50",
                "minerals": "/api_v1/minerals?name=quartz&limit=20",
                "mindat_localities": "/api_v1/loc?taxon=quartz&run=mindat&limit=20",
                "timebound": "/api_v1/misc/timebound?agerange=pleistocene",
            },
        }
    )


@app.get("/api_v1/occ")
def occurrences():
    taxon = request.args.get("taxon")
    if not taxon:
        return jsonify(
            {
                "type": "about:blank",
                "title": "Bad Request",
                "detail": "Parameter required: taxon (or use bbox/agerange in a fuller port)",
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
    dbs = _run_list(request.args.get("run"))

    records: list[dict[str, Any]] = []
    meta = _base_meta(ageunits, coordtype, includelower)
    errors: dict[str, str] = {}

    if "pbdb" in dbs:
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

    if "neotoma" in dbs:
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

    if "mindat" in dbs:
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
    dbs = _run_list(request.args.get("run"))
    show = (request.args.get("show") or "all").lower()

    if not taxon and not agerange:
        return jsonify(
            {
                "detail": "Provide taxon and/or agerange",
                "status": 400,
            }
        ), 400

    records: list[dict[str, Any]] = []
    meta = _base_meta(ageunits, "modern", True)

    if "pbdb" in dbs:
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

    if show == "poll":
        return jsonify(meta)
    return jsonify(metadata=meta, records=records)


@app.get("/api_v1/minerals")
def minerals():
    """Mindat geomaterials search (requires MINDAT_API_KEY)."""
    name = request.args.get("name") or request.args.get("mineral")
    if not name:
        return jsonify({"detail": "Parameter required: name", "status": 400}), 400
    if not mindat_configured():
        return jsonify(
            {
                "detail": "Mindat is currently disabled in this API.",
                "status": 503,
                "mindat_enabled": mindat_enabled(),
                "hint": (
                    "When your Mindat account is active, add to key.env:\n"
                    "MINDAT_ENABLED=true\n"
                    "(and keep your token in key.env)"
                ),
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
