# TODO

Remaining code quality improvements that still need follow-up.

## utils/post_data.py

- **Misleading variable name**: In the prod sync path, `dev` holds the response fetched from the dev API before posting to prod. Consider renaming it to `dev_response` or another context-appropriate name.
  ```python
  # Current:
  dev = httpx.get(...)  # This is actually fetching from dev to push to prod
  prod = httpx.post(...)
  ```

## Output size optimization

- **Compact array format**: Replace full GeoJSON feature objects with compact `[lon, lat, "city"]` arrays in the output. Reconstruct GeoJSON on the consumer side. This would reduce output size by ~70-80% (273 KB → ~70 KB across all providers) since the repeated `{"type":"Feature","geometry":{"type":"Point","coordinates":[...]},"properties":{"city":"..."}}` boilerplate accounts for ~80% of each file. Requires a corresponding change in the frontend/API consumer to unpack the arrays back into GeoJSON.
