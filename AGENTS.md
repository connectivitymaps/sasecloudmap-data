# AGENTS.md (CLAUDE.md)

## Project Overview

This repository collects and transforms SASE/CDN provider datacenter location data into GeoJSON format for display on [sasecloudmap.com](https://sasecloudmap.com/). Each provider script scrapes location data from public sources, geocodes it, and pushes it to dev/prod environments via API.

## Tech Stack

- **Python 3.13+** with **uv** for package management
- **httpx** - HTTP client for API requests
- **BeautifulSoup4** - HTML parsing for scraping provider docs
- **Playwright** - Browser automation (used by Forcepoint scraper)
- **python-dotenv** - Environment variable management
- **ruff** - Linting and formatting

## Repository Structure

```
provider-data/
├── provider_data/           # Main package
│   ├── *.py                 # Provider scripts (one per SASE vendor)
│   ├── run_all.py           # Batch runner for all providers
│   └── utils/
│       ├── post_data.py     # API posting helper
│       ├── skeleton.py      # GeoJSON skeleton generator
│       ├── generate_sitemap.py  # Sitemap generation utility
│       └── upload_to_r2.py  # R2 historical snapshot uploader
├── tests/                   # GeoJSON validation tests
├── output/                  # Generated JSON files (gitignored)
├── .github/workflows/       # CI: auto-update dev/prod on schedule
├── pyproject.toml           # Project dependencies
└── .env                     # Environment config (not committed)
```

## Provider Scripts Pattern

Each `provider_data/*.py` script follows this structure:

1. **`get_data()`** - Fetches raw location data from provider's public source
2. **`convert_to_geojson(data)`** - Transforms data to GeoJSON features
3. **CLI interface** with `--refresh`, `--dev`, `--prod` flags
4. Uses `utils.skeleton.geojson_skeleton()` to wrap features
5. Uses `utils.post_data.write_and_post()` to push to environments

## Key Commands

```bash
# Setup
source .venv/bin/activate
cp .env.example .env  # Then fill in credentials

# Refresh data from sources
uv run provider_data/<provider>.py --refresh

# Push to dev environment
uv run provider_data/<provider>.py --dev

# Push to prod environment
uv run provider_data/<provider>.py --prod

# Batch operations (recommended)
uv run provider_data/run_all.py --refresh --dev

# Run tests
uv run pytest tests/ -v

# Linting
uv run ruff check --fix
uv run ruff format
```

## Environment Variables

Required in `.env`:
- `AUTH` - API authentication token
- `BMS` - Additional auth header
- `DEV_HOSTNAME` - Dev API endpoint (e.g., `https://dev.example.com/add`)
- `PROD_HOSTNAME` - Prod API endpoint
- `CLOUDFLARE_ZONE_ID` - For cache purging
- `CACHE_PURGE_KEY` - Cloudflare API token for cache operations
- `R2_ACCOUNT_ID` - Cloudflare account ID (for R2 snapshots)
- `R2_ACCESS_KEY_ID` - R2 API token access key ID
- `R2_SECRET_ACCESS_KEY` - R2 API token secret access key
- `R2_BUCKET_NAME` - R2 bucket name for historical snapshots

## Current Providers

| Provider | Script | Data Source |
|----------|--------|-------------|
| Cloudflare | `cloudflare_geojson.py` | speed.cloudflare.com API |
| Zscaler | `zscaler_geojson.py` | config.zscaler.com API |
| Netskope | `netskope_geojson.py` | trust.netskope.com API |
| Palo Alto | `paloalto_geojson.py` | docs.paloaltonetworks.com (HTML scrape) |
| Fortinet | `fortinet_geojson.py` | docs.fortinet.com (HTML scrape) |
| Check Point | `checkpoint_geojson.py` | sc1.checkpoint.com (HTML scrape) |
| Cisco Umbrella | `cisco_umbrella_geojson.py` | umbrella.cisco.com (HTML scrape) |
| Cato Networks | `catonetworks.py` | support.catonetworks.com (CSV) |
| iboss | `iboss_geojson.py` | status.iboss.com API |
| Forcepoint | `forcepoint_geojson.py` | support.forcepoint.com (Playwright) |

## Adding a New Provider

1. Create `provider_data/<provider>_geojson.py`
2. Implement `get_data()` to fetch locations from source
3. Implement `convert_to_geojson(data)` following existing pattern
4. Add standard CLI with `--refresh`, `--dev`, `--prod` flags
5. Set `provider_name`, `friendly_name`, `app_type` variables
6. Test with `--refresh` then `--dev`

## GeoJSON Output Format

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [longitude, latitude]
      },
      "properties": {
        "city": "Location Name"
      }
    }
  ]
}
```

## CI/CD

- **update_dev_unified.yaml** - Runs on push to main + weekly schedule (Monday 18:00 UTC)
- **update_main.yaml** - Production deployment workflow
- Uses `run_all.py` for batch updates with graceful failure handling
- Runs GeoJSON validation tests after updates
- Generates sitemap and purges Cloudflare cache
- Uploads historical GeoJSON snapshots to Cloudflare R2 (timestamp-prefixed)

## Common Geocoding Services Used

- **nominatim.openstreetmap.org** - Primary geocoding for city names
- **iata.clumsy.dev** - Airport code to coordinates lookup
- **ipinfo.io** - IP geolocation (for Cloudflare China IPs)

## Notes for AI Agents

- Scripts are executable via shebang: `#!/usr/bin/env -S uv run`
- Coordinate order varies: some sources use `[lat, lon]`, output is always `[lon, lat]` for GeoJSON
- Many scripts use deduplication: `[i for n, i in enumerate(x) if i not in x[n+1:]]`
- Error handling catches HTTP and parsing errors, logs failures but continues
- Nominatim rate limiting (1 req/sec) is implemented in all provider scripts
