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

3. In `create_migration`, replace the hardcoded `"mirror_interval": "0h10m0s"`
   with the computed value:

   ```python
   "mirror_interval": to_gitea_duration(MIRROR_INTERVAL_MINUTES),
   ```

   `create_migration` itself does not need a new parameter — both call sites
   in `main()` should use the same global interval, since both mirrors
   (external → `MIRROR_SERVER_URL`, and `MIRROR_SERVER_URL` →
   `WORKSPACE_SERVER_URL`) are expected to stay in sync on the same cadence.

### Validation

- Reject non-positive values (`MIRROR_INTERVAL_MINUTES <= 0`) at startup with
  a clear error, since a zero/negative interval either disables mirroring
  (Gitea semantics for `"0"`) or is meaningless — surfacing this as a
  configuration error avoids silently mirroring in an unintended way.
- `int(os.environ.get(...))` will already raise `ValueError` for non-numeric
  input, which is acceptable given the project's existing style (other env
  vars, like `REPOSITORY_DATA`, also fail fast via `json.loads` without
  custom error handling).

### Documentation updates

- `README.md`: add `MIRROR_INTERVAL_MINUTES` to the "Environment Variables"
  list, documenting it as optional with a default of `10`.

### Testing

- No existing test suite is present in the repository. If one is added
  later, `to_gitea_duration` is a pure function and easy to unit test
  (e.g. `10 -> "0h10m0s"`, `90 -> "1h30m0s"`, `0 -> "0h0m0s"`).
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
