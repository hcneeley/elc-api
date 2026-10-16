# ELC-compatible API

A local recreation of the [Earth-Life Consortium API](https://github.com/EarthLifeConsortium/elc_api) that composites:

- [Paleobiology Database (PBDB)](https://paleobiodb.org/)
- [Neotoma Paleoecology Database](https://www.neotomadb.org/)
- [Mindat](https://www.mindat.org/) (optional; disabled by default until API access is active)

## Live deployment

**Base URL:** https://elc-api-i83q.onrender.com/api_v1/

| Endpoint | Example |
|----------|---------|
| Index | https://elc-api-i83q.onrender.com/api_v1/ |
| Occurrences | https://elc-api-i83q.onrender.com/api_v1/occ?taxon=canis+dirus&limit=5 |
| Taxonomy | https://elc-api-i83q.onrender.com/api_v1/tax?taxon=canis+dirus |
| Locales | https://elc-api-i83q.onrender.com/api_v1/loc?taxon=canis+dirus&limit=20 |
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

Native upstream bases used by this service:

- PBDB: `https://paleobiodb.org/data1.2/`
- Neotoma: `https://api.neotomadb.org/v2.0/data/`
- Mindat: `https://api.mindat.org/v1/` (when enabled)

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

### Example queries (local)

```bash
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&limit=20"
curl "http://127.0.0.1:8008/api_v1/tax?taxon=canis+dirus"
curl "http://127.0.0.1:8008/api_v1/misc/timebound?agerange=pleistocene"
```

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
| `/api_v1/occ` | Fossil occurrences (PBDB + Neotoma; Mindat if enabled) |
| `/api_v1/tax` | Taxonomy |
| `/api_v1/loc` | Locales / collections |
| `/api_v1/minerals` | Mindat geomaterials (when enabled) |
| `/api_v1/misc/timebound` | Geologic age bounds via PBDB |
