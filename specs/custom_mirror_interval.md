# Configurable Mirror Interval

## Problem

`create_migration` in `gitea_mirror_manager/mirrors.py` hardcodes the Gitea
`mirror_interval` field:

```python
data: dict[str, str | bool] = {
    ...
    "mirror_interval": "0h10m0s",
    ...
}
```

This value should be configurable via an environment variable instead of a
fixed 10 minutes, following the same convention already used for
`MIRROR_SERVER_URL`, `WORKSPACE_SERVER_URL`, `REPOSITORY_DATA`, etc.

## Gitea constraint

Gitea's `mirror_interval` is a Go duration string (e.g. `"0h10m0s"`,
`"1h0m0s"`). A value of `"0"` disables periodic sync. The implementation must
produce a value in this format regardless of how the environment variable is
expressed.

## Proposed change

### New environment variable: `MIRROR_INTERVAL_MINUTES`

- Optional, integer, expressed in minutes for simplicity (matches the
  existing hardcoded value's unit).
- Default: `10` (preserves current behaviour when unset).
- Read once at module load time, alongside the other configuration constants
  near the top of `mirrors.py`.

### Code changes in `gitea_mirror_manager/mirrors.py`

1. Add a new module-level constant next to the other server configuration:

   ```python
   DEFAULT_MIRROR_INTERVAL_MINUTES: int = 10
   MIRROR_INTERVAL_MINUTES: int = int(
       os.environ.get("MIRROR_INTERVAL_MINUTES", DEFAULT_MIRROR_INTERVAL_MINUTES)
   )
   ```

2. Add a small helper to convert minutes to Gitea's duration string:

   ```python
   def to_gitea_duration(minutes: int) -> str:
       hours, remaining_minutes = divmod(minutes, 60)
       return f"{hours}h{remaining_minutes}m0s"
   ```

3. Give `create_migration` a new required parameter, `mirror_interval_minutes:
   int`, instead of reaching for the module-level constant directly:

   ```python
   def create_migration(
       repository_url: str,
       repository_name: str,
       repository_auth_token: str,
       gitea_url: str,
       token: str,
       service: str,
       mirror_interval_minutes: int,
   ) -> tuple[Any, Any]:
       ...
       data: dict[str, str | bool] = {
           "clone_addr": repository_url,
           "auth_token": repository_auth_token,
           "mirror": True,
           "mirror_interval": to_gitea_duration(mirror_interval_minutes),
           "private": False,
           "repo_name": repository_name,
           "service": service,
       }
       ...
   ```

   Both call sites in `main()` pass `MIRROR_INTERVAL_MINUTES` explicitly, so
   the two mirror legs (external → `MIRROR_SERVER_URL`, and
   `MIRROR_SERVER_URL` → `WORKSPACE_SERVER_URL`) stay in sync on the same
   cadence, while keeping `create_migration` free of a hidden dependency on
   module-level state — this also makes it straightforward to unit test with
   different interval values.

### Validation

- Reject values that are not strictly greater than 1 minute
  (`MIRROR_INTERVAL_MINUTES <= 1`) at startup with a clear error. A value of
  `0` or `1` is rejected: `0` disables periodic sync entirely (Gitea
  semantics), and `1` minute is too aggressive/meaningless for this use case,
  so both are treated as configuration errors rather than silently accepted.
- Perform this check once, right after reading the environment variable, e.g.:

  ```python
  if MIRROR_INTERVAL_MINUTES <= 1:
      error_message = (
          "MIRROR_INTERVAL_MINUTES must be bigger than 1 minute, "
          f"got {MIRROR_INTERVAL_MINUTES}."
      )
      raise ValueError(error_message)
  ```

- `int(os.environ.get(...))` will already raise `ValueError` for non-numeric
  input, which is acceptable given the project's existing style (other env
  vars, like `REPOSITORY_DATA`, also fail fast via `json.loads` without
  custom error handling).

### Documentation updates

- `README.md`: add `MIRROR_INTERVAL_MINUTES` to the "Environment Variables"
  list, documenting it as optional, with a default of `10`, and that it must
  be greater than `1`.

### Testing

No test suite currently exists in the repository (`pyproject.toml` already
has `tool.ruff.lint.per-file-ignores` entries for `tests/**/*`, but no `tests/`
directory or test runner is configured yet). Add a minimal one scoped to this
feature only — not a general test suite for the whole module:

- Add `pytest` to a `[tool.hatch.envs.test]` section in `pyproject.toml`
  (mirroring the existing `lint` env), with a `run = "pytest {args:tests}"`
  script.
- Add `tests/test_mirrors.py` covering only the mirror-interval behaviour:
  - `to_gitea_duration`: pure-function cases, e.g. `10 -> "0h10m0s"`,
    `90 -> "1h30m0s"`, `120 -> "2h0m0s"`.
  - Startup validation: reloading the module (or extracting the check into a
    small `validate_mirror_interval_minutes(value: int) -> None` function
    that the module-level code calls) with `MIRROR_INTERVAL_MINUTES` set to
    `0` and `1` raises `ValueError`; `2` and `10` do not raise.
  - `create_migration`: with `requests.post` mocked (`unittest.mock.patch`),
    assert that the JSON body sent to Gitea contains
    `"mirror_interval": to_gitea_duration(mirror_interval_minutes)` for the
    `mirror_interval_minutes` value passed in, confirming the parameter is
    threaded through correctly rather than falling back to a hardcoded value.
- Out of scope for this test suite: `create_token`, `delete_token`,
  `get_repositories`, `delete_repository`, `obtain_api_token`, and `main` —
  none of these are touched by this change and adding tests for them is a
  separate effort.
- Manual verification: run the container with `MIRROR_INTERVAL_MINUTES=30`
  set and confirm the created migration's `mirror_interval` field reflects
  `"0h30m0s"` via the Gitea API response or UI.

## Out of scope

- Making the interval configurable independently per mirror leg (mirror
  server vs. workspace server) — not requested, and the two servers are
  expected to share one cadence.
- Supporting arbitrary duration strings (e.g. `"1h30m"`) directly via the
  environment variable — minutes-as-integer keeps the interface simple and
  consistent with the value it replaces.
