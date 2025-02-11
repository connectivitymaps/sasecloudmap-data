# SASE Cloud Map: Data Repository

This repo contains the data for the individual provider's displayed on [sasecloudmap.com](https://sasecloudmap.com/)

## usage

1. copy `.env.example` to `.env` and edit `.env` file with the required environment variables

```shell
# load python environment
source .venv/bin/activate
# refresh data
for i in src/provider_data/*.py; do echo $i; $i --refresh; done
# update dev environment
for i in src/provider_data/*.py; do echo $i; $i --dev; done
# update prod environment
for i in src/provider_data/*.py; do echo $i; $i --prod; done
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
