# ELC-compatible API

A local recreation of the [Earth-Life Consortium API](https://github.com/EarthLifeConsortium/elc_api) that composites:

- [Paleobiology Database (PBDB)](https://paleobiodb.org/)
- [Neotoma Paleoecology Database](https://www.neotomadb.org/)
- [Mindat](https://www.mindat.org/) (optional; disabled by default until API access is active)

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

API root: http://127.0.0.1:8008/api_v1/

### Example queries

```bash
curl "http://127.0.0.1:8008/api_v1/occ?taxon=canis+dirus&limit=20"
curl "http://127.0.0.1:8008/api_v1/tax?taxon=canis+dirus"
curl "http://127.0.0.1:8008/api_v1/misc/timebound?agerange=pleistocene"
```

### Client script

```bash
python earthlife_consortium_api.py
```

Writes summaries, CSV, and plots under `output/`.

## Mindat (optional)

Mindat is **off by default**. When your Mindat account is approved for API use, put this in a local `key.env` (never commit it):

```env
MINDAT_ENABLED=true
MINDAT_API_KEY=your_token_here
```

On Mac, Finder may not allow naming a file `.env`; `key.env` is supported.

## Deploy (Render)

See `render.yaml`. Set secrets in the Render dashboard; do not commit API keys.

## Endpoints

| Path | Description |
|------|-------------|
| `/api_v1/occ` | Fossil occurrences (PBDB + Neotoma; Mindat if enabled) |
| `/api_v1/tax` | Taxonomy |
| `/api_v1/loc` | Locales / collections |
| `/api_v1/minerals` | Mindat geomaterials (when enabled) |
| `/api_v1/misc/timebound` | Geologic age bounds via PBDB |
