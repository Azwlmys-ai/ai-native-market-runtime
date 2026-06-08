# DXY Manual Input Spec (Observation Only)

**Principle:** Observation ≠ Experience. Do not promote to trading rules.

## Target file

`data/historical/dxy_daily.jsonl` (copy from `dxy_daily.jsonl.example`)

## Required fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | `YYYY-MM-DD` |
| `close` | float | DXY or USD index close |
| `observation_only` | bool | must be `true` |

## Optional fields

- `symbol` (default `DXY`)
- `source` (e.g. `yahoo^DXY`, `fred_DTWEXBGS`, `manual_csv_import`)
- `open`, `high`, `low`, `volume`

## Example JSONL line

```json
{"date": "2026-01-02", "close": 103.45, "symbol": "DXY", "source": "manual_csv_import", "observation_only": true}
```

## Catalog

- `macro.dxy.daily` → graceful `insufficient_data` when file missing
- No network fetch in Phase 3d builders
