# SASE Cloud Map: Data Repository

This repo contains the data for the individual provider's displayed on [sasecloudmap.com](https://sasecloudmap.com/)

## usage

1. copy `.env.example` to `.env` and edit `.env` file with the required environment variables
2. for Browser Rendering-backed providers such as Forcepoint, use a Cloudflare token with `Browser Rendering - Edit`

```shell
# refresh and update all providers
uv run provider_data/run_all.py --refresh --dev

# or run individual provider
uv run provider_data/cloudflare_geojson.py --refresh --dev

# run tests
uv run pytest tests/ -v
```

## browser rendering

- `provider_data/utils/browser_rendering.py` wraps Cloudflare Browser Rendering quick actions for reusable scraping flows
- `provider_data/forcepoint_geojson.py` now uses Browser Rendering `/json` first, with a markdown fallback
- `BROWSER_RENDERING_API_TOKEN` is optional and falls back to `CLOUDFLARE_API_TOKEN`
- `BROWSER_RENDERING_JSON_MODEL` defaults to `workers-ai/@cf/moonshotai/kimi-k2.5`
- `CLOUDFLARE_ACCOUNT_ID` and `R2_ACCOUNT_ID` should be bare account IDs, without a trailing `/`

## help

```shell
uv run provider_data/cloudflare_geojson.py -h
```

## misc

```shell
uv run ruff check --fix
uv run ruff format
```
