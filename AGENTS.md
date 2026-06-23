# AGENTS.md

## Purpose

This app fetches SASE provider location data, converts it to GeoJSON, writes `output/<provider>.json`, and posts it to the `sasecloudmap` Worker API.

Use `uv` for all Python commands. Do not use ambient `python`, `pip`, or global tools.

## Important Files

- `provider_data/*_geojson.py`: one provider script per vendor.
- `provider_data/utils/base.py`: shared GeoJSON conversion for simple `{name, coordinates}` provider data.
- `provider_data/utils/output.py`: validates and atomically writes generated GeoJSON. Do not bypass it.
- `provider_data/utils/post_data.py`: posts dev/prod payloads to the frontend Worker.
- `provider_data/run_all.py`: local batch runner. `--refresh` runs one provider at a time to respect geocoder throttling.
- `provider_data/utils/provider_discovery.py`: source of truth for workflow provider discovery.
- `.github/workflows/update_dev_unified.yaml`: CI refreshes individual provider scripts, validates output, deploys eligible outputs to dev, then generates the dev sitemap.
- `.github/workflows/update_main.yaml`: production workflow posts from dev to prod. Do not touch prod behavior unless asked.

## Provider Script Contract

Each provider script should keep this shape:

- literal top-level `provider_name`, `friendly_name`, and `app_type`
- CLI flags `--refresh`, `--dev`, `--prod`
- `--refresh` fetches source data and writes `output/<provider_name>.json`
- `--dev` posts local output to `DEV_HOSTNAME`
- `--prod` reads the current dev API data and posts it to `PROD_HOSTNAME`

Generated output must be:

- GeoJSON `FeatureCollection`
- Point features with coordinates in `[longitude, latitude]` order
- non-empty when written or posted
- backward-compatible with current frontend consumers unless `sasecloudmap` is changed in the same task

## GeoJSON Property Contract

Current frontend code depends on `properties.city`.

If changing output properties:

- keep `city` populated during rollout, or update frontend fallbacks at the same time
- preserve Cloudflare route lookup behavior in `../sasecloudmap/src/connectionRoute.js`
- update comparison behavior in `../sasecloudmap/src/tableData.js` when grouping keys change
- add or update tests in both apps

For location comparison normalization, prefer deterministic coordinate-based behavior. Do not add LLM normalization, broad alias tables, or fuzzy string matching as the primary matching mechanism.

See `docs/location-comparison-normalization-prd.md` before changing comparison-facing GeoJSON fields.

## Commands

```shell
uv sync --all-extras --dev
uv run provider_data/<provider>.py --refresh
uv run provider_data/run_all.py --refresh --fail-on-any-failure
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
```

Use `--dev` only when the task requires posting to staging/dev. Use `--prod` only when explicitly requested.

## Safety Rules

- Never commit `.env`, tokens, provider credentials, R2 keys, or workflow secrets.
- Keep `output/` generated. Edit provider scripts or shared utilities, not generated JSON, unless the user explicitly asks for a one-off local artifact.
- Do not relax empty-output protections in `provider_data/utils/output.py` or `provider_data/utils/post_data.py`.
- If a provider source or parser changed, reproduce with the single provider first, then run the narrow tests.
- If the change affects workflows, update `tests/test_workflow_ci.py`.
