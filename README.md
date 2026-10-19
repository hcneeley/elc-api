# ELC-compatible API

A local recreation of the [Earth-Life Consortium API](https://github.com/EarthLifeConsortium/elc_api) that composites:

- [Paleobiology Database (PBDB)](https://paleobiodb.org/)
- [Neotoma Paleoecology Database](https://www.neotomadb.org/)
- [Macrostrat](https://macrostrat.org/) — stratigraphic units at a lat/lng
- [Mindat](https://www.mindat.org/) (optional; enabled when `MINDAT_ENABLED=true` and a key is set)
- [ePANDDA](https://epandda.org/) — correlates [PBDB](https://paleobiodb.org/) occurrences with [iDigBio](https://www.idigbio.org/) specimens

## Live deployment

**Base URL:** https://elc-api-i83q.onrender.com/api_v1/

| Endpoint | Example |
|----------|---------|
| Index | https://elc-api-i83q.onrender.com/api_v1/ |
| Occurrences | https://elc-api-i83q.onrender.com/api_v1/occ?taxon=canis+dirus&limit=5 |
| Taxonomy | https://elc-api-i83q.onrender.com/api_v1/tax?taxon=canis+dirus |
| Locales | https://elc-api-i83q.onrender.com/api_v1/loc?taxon=canis+dirus&limit=20 |
| Macrostrat | https://elc-api-i83q.onrender.com/api_v1/macrostrat?lat=43.07&lng=-89.4&limit=10 |
| ePANDDA | https://elc-api-i83q.onrender.com/api_v1/epandda?terms=hadrosaurus&limit=10 |
| Minerals (Mindat) | https://elc-api-i83q.onrender.com/api_v1/minerals?name=quartz&limit=5 |
| Time bounds | https://elc-api-i83q.onrender.com/api_v1/misc/timebound?agerange=pleistocene |

> Free Render tier: the service may sleep when idle. The first request after a pause can take ~30–60 seconds.

## Upstream API documentation

This service calls the following databases. Use these docs when extending queries or debugging upstream responses:

| Database | What it provides here | Documentation |
|----------|----------------------|---------------|
| **Earth-Life Consortium (original)** | Schema / response shape this API recreates | [ELC API docs](http://earthlifeconsortium.org/docs/api-docs.html) · [elc_api on GitHub](https://github.com/EarthLifeConsortium/elc_api) |
| **Paleobiology Database (PBDB)** | Fossil occurrences, taxonomy, collections, age intervals | [PBDB data service](https://paleobiodb.org/data1.2/) · [PBDB API overview](https://paleobiodb.org/#/) |
| **Neotoma** | Paleoecological occurrences and taxa | [Neotoma APIv2](https://api.neotomadb.org/) · [Neotoma Database](https://www.neotomadb.org/) · [Manual / help](https://open.neotomadb.org/) |
| **Mindat** (optional) | Minerals / geomaterials and localities | [OpenMindat API (ReDoc)](https://api.mindat.org/v1/schema/redoc/) · [How to use Mindat API](https://github.com/ChuBL/How-to-Use-Mindat-API) · [Get an API key](https://www.mindat.org/a/how_to_get_my_mindat_api_key) |
| **ePANDDA** | Correlated PBDB occurrences + iDigBio specimens | [ePANDDA docs](https://epandda.org/documentation_2.html) · [iDigBio search API](https://github.com/iDigBio/idigbio-search-api/wiki) |
| **Macrostrat** | Stratigraphic units (lithology, age, thickness) at a point | [Macrostrat API](https://macrostrat.org/api) |

Native upstream bases used by this service:

- PBDB: `https://paleobiodb.org/data1.2/`
- Neotoma: `https://api.neotomadb.org/v2.0/data/`
- Mindat: `https://api.mindat.org/v1/` (when enabled)
- ePANDDA: `https://api.epandda.org/` (falls back to PBDB + `https://search.idigbio.org/v2/` when the host is down)
- Macrostrat: `https://macrostrat.org/api/v2/`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run locally

```bash
python -m elc_server.app
```

Local API root: http://127.0.0.1:8008/api_v1/

Use `run=` on `/occ`, `/tax`, and `/loc` to pick backends (`pbdb`, `neotoma`, `mindat`, `epandda`, `macrostrat`, or `all`). Defaults are `neotoma,pbdb` unless noted below.

## Test the live API

```bash
bash test_elc_api.sh
```

Or point at another deployment:

```bash
BASE=https://elc-api-i83q.onrender.com/api_v1 bash test_elc_api.sh
```

## Client script

```bash
export ELC_BASE=https://elc-api-i83q.onrender.com/api_v1
python earthlife_consortium_api.py
```

Writes summaries, CSV, and plots under `output/`.

## Endpoints

| Path | Description |
|------|-------------|
| `/api_v1/occ` | Fossil / mineral / stratigraphic records (`run=` selects backends) |
| `/api_v1/tax` | Taxonomy (PBDB + Neotoma) |
| `/api_v1/loc` | Locales / collections (or Macrostrat units via `lat`+`lng`) |
| `/api_v1/minerals` | Mindat geomaterials (when configured) |
| `/api_v1/epandda` | ePANDDA-shaped PBDB + iDigBio correlated results (`terms=…`) |
| `/api_v1/macrostrat` | Macrostrat stratigraphic units at `lat`+`lng` |
| `/api_v1/misc/timebound` | Geologic age bounds via PBDB |

### Paleobiology Database (PBDB)

[PBDB](https://paleobiodb.org/) provides collection-based fossil occurrences, taxonomy, and named geologic intervals. It is included by default on `/occ`, `/tax`, and `/loc`. Docs: [data service](https://paleobiodb.org/data1.2/).

```bash
# Occurrences / taxonomy / locales (default run includes pbdb)
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&limit=20"
curl "http://127.0.0.1:8008/api_v1/tax?taxon=canis+dirus"
curl "http://127.0.0.1:8008/api_v1/loc?taxon=canis+dirus&limit=20"

# PBDB only
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&run=pbdb&limit=20"

# Resolve a named age range via PBDB intervals
curl "http://127.0.0.1:8008/api_v1/misc/timebound?agerange=pleistocene&ageunits=ma"
```

### Neotoma

[Neotoma](https://www.neotomadb.org/) provides paleoecological occurrences and taxa (often Quaternary). It is included by default alongside PBDB. Docs: [APIv2](https://api.neotomadb.org/).

```bash
# Default composite (neotoma + pbdb)
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&limit=20"
curl "http://127.0.0.1:8008/api_v1/tax?taxon=canis+dirus"
curl "http://127.0.0.1:8008/api_v1/loc?taxon=canis+dirus&limit=20"

# Neotoma only
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&run=neotoma&limit=20"
```

### Mindat

[Mindat](https://www.mindat.org/) provides mineral / geomaterial records and localities via the OpenMindat API. Requires `MINDAT_API_KEY` (local `key.env`, or a Render secret file / env var). Docs: [ReDoc](https://api.mindat.org/v1/schema/redoc/) · [API key](https://www.mindat.org/a/how_to_get_my_mindat_api_key).

```bash
# Geomaterials search
curl "http://127.0.0.1:8008/api_v1/minerals?name=quartz&limit=20"

# Localities / occurrences via run=mindat
curl "http://127.0.0.1:8008/api_v1/loc?taxon=quartz&run=mindat&limit=20"
curl "http://127.0.0.1:8008/api_v1/occ?taxon=quartz&run=mindat&limit=20"
```

On Render, mount the token as a **Secret File** named `MINDAT_API_KEY` (or set the environment variable of the same name) and keep `MINDAT_ENABLED=true`.

### ePANDDA

[ePANDDA](https://epandda.org/) links PBDB collection-based occurrences with iDigBio specimen records (taxonomy, locality, chronostratigraphy). Query with `terms=` using bare text or `field:value` pairs separated by `|` (see [docs](https://epandda.org/documentation_2.html)).

```bash
# Native ePANDDA-shaped response
curl "http://127.0.0.1:8008/api_v1/epandda?terms=hadrosaurus&limit=10"
curl "http://127.0.0.1:8008/api_v1/epandda?terms=genus:hadrosaurus|country:canada"

# Same data flattened into /occ records
curl "http://127.0.0.1:8008/api_v1/occ?taxon=hadrosaurus&run=epandda&limit=20"
```

If `api.epandda.org` is unreachable, this service composes the same pairing from PBDB + iDigBio directly.

### Macrostrat

[Macrostrat](https://macrostrat.org/) returns stacked stratigraphic units at a map point (ages in Ma, lithology, environment, PBDB counts). Docs: [Macrostrat API](https://macrostrat.org/api).

```bash
curl "http://127.0.0.1:8008/api_v1/macrostrat?lat=43.07&lng=-89.4&limit=20"
curl "http://127.0.0.1:8008/api_v1/loc?lat=43.07&lng=-89.4"
curl "http://127.0.0.1:8008/api_v1/occ?lat=43.07&lng=-89.4&run=macrostrat&limit=20"
```

Point-only `/loc` and `/occ` queries (lat+lng, no taxon) default to Macrostrat.
