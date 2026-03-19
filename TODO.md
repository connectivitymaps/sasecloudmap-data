# TODO

Remaining code quality improvements that still need follow-up.

## utils/post_data.py

- **Misleading variable name**: In the prod sync path, `dev` holds the response fetched from the dev API before posting to prod. Consider renaming it to `dev_response` or another context-appropriate name.
  ```python
  # Current:
  dev = httpx.get(...)  # This is actually fetching from dev to push to prod
  prod = httpx.post(...)
  ```
