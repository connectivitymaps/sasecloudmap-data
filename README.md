# SASE Cloud Map: Data Repository

This repo contains the data for the individual provider's displayed on [sasecloudmap.com](https://sasecloudmap.com/)

## usage

1. copy `.env.example` to `.env` and edit `.env` file with the required environment variables

```shell
# refresh and update all providers
uv run provider_data/run_all.py --refresh --dev

# or run individual provider
uv run provider_data/cloudflare_geojson.py --refresh --dev

# run tests
uv run pytest tests/ -v
```

## help

```shell
src/provider_data/cloudflare_geojson.py -h
```

## misc

```shell
uv run ruff check --fix
uv run ruff format
```
