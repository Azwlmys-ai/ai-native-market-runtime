"""
Observation Catalog Loader — Phase 2 read-only cross-project observation access.

Principle: Share Observation, not Experience.
- Allowlist / denylist enforcement via cross_project_data_catalog.json
- Schema validation (lightweight required-field checks)
- Read-only: never writes to source projects or forbidden targets
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

_DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "research" / "cross_project_data_catalog.json"

_EXPERIENCE_PATH_HINTS = (
    "experience",
    "lessons",
    "knowledge",
    "learned_rules",
    "learning_knowledge_base",
    "rule_effectiveness",
    "model_effectiveness",
    "learning_feedback",
    "experience_review",
    "cell_attribution",
    "oos_candidates",
)


class CatalogError(Exception):
    """Observation catalog access violation or validation failure."""


@dataclass(frozen=True)
class CatalogEntry:
    catalog_id: str
    source_project: str
    path: Path | None
    path_glob: str | None
    category: str
    data_type: str
    schema_path: Path | None
    status: str
    safety_flag: str | None = None
    record_count: int | None = None

    def resolve_paths(self) -> list[Path]:
        if self.path and self.path.exists():
            return [self.path]
        if self.path_glob:
            root = self.path_glob.split("*", 1)[0]
            pattern = self.path_glob
            base = Path(root).parent if root else Path("/")
            if not base.exists():
                return []
            matches: list[Path] = []
            for p in base.rglob("*"):
                if fnmatch.fnmatch(str(p), pattern):
                    matches.append(p)
            return sorted(matches)
        if self.path:
            return [self.path]
        return []


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_catalog(catalog_path: Path | None = None) -> dict:
    path = catalog_path or _DEFAULT_CATALOG
    return _load_json(path)


class ObservationCatalog:
    """Read-only loader for cross-project observation assets."""

    def __init__(self, catalog_path: Path | None = None):
        self.catalog_path = catalog_path or _DEFAULT_CATALOG
        self._catalog = load_catalog(self.catalog_path)
        self._allow = {e["catalog_id"]: e for e in self._catalog.get("allowlist", [])}
        self._deny = self._catalog.get("denylist", [])
        self._policy = self._catalog.get("access_policy", {})

    @property
    def principle(self) -> str:
        return self._catalog.get("principle", "Share Observation, not Experience")

    @property
    def shared_root(self) -> Path:
        return Path(self._catalog.get("shared_root", "/Users/libo/shared_intelligence"))

    def list_allowlist(self) -> list[CatalogEntry]:
        return [self._to_entry(e) for e in self._catalog.get("allowlist", [])]

    def get_entry(self, catalog_id: str) -> CatalogEntry:
        if catalog_id not in self._allow:
            raise CatalogError(f"catalog_id not in allowlist: {catalog_id}")
        return self._to_entry(self._allow[catalog_id])

    def _to_entry(self, raw: dict) -> CatalogEntry:
        return CatalogEntry(
            catalog_id=raw["catalog_id"],
            source_project=raw.get("source_project", ""),
            path=Path(raw["path"]) if raw.get("path") else None,
            path_glob=raw.get("path_glob"),
            category=raw.get("category", "A"),
            data_type=raw.get("data_type", ""),
            schema_path=Path(raw["schema"]) if raw.get("schema") else None,
            status=raw.get("status", "unknown"),
            safety_flag=raw.get("safety_flag"),
            record_count=raw.get("record_count"),
        )

    def _is_denied_path(self, path: Path) -> str | None:
        s = str(path.resolve()) if path.exists() else str(path)
        for item in self._deny:
            if item.get("path") and s == str(Path(item["path"]).resolve()):
                return item.get("reason", "denylist")
            glob = item.get("path_glob")
            if glob and fnmatch.fnmatch(s, glob):
                return item.get("reason", "denylist")
            if glob and "**" in glob:
                # simple ** match
                pat = glob.replace("**/", "").replace("**", "*")
                if fnmatch.fnmatch(Path(s).name, pat) or fnmatch.fnmatch(s, glob):
                    return item.get("reason", "denylist")
        lower = s.lower()
        for hint in _EXPERIENCE_PATH_HINTS:
            if hint in lower and "observation" not in lower:
                if any(hint in str(d.get("path", "")).lower() or hint in str(d.get("path_glob", "")).lower()
                       for d in self._deny):
                    continue
        return None

    def assert_read_allowed(self, catalog_id: str, resolved_path: Path) -> None:
        if self._policy.get("require_catalog_id") and not catalog_id:
            raise CatalogError("catalog_id required")
        if catalog_id not in self._allow:
            raise CatalogError(f"not in allowlist: {catalog_id}")
        reason = self._is_denied_path(resolved_path)
        if reason:
            raise CatalogError(f"denied path ({reason}): {resolved_path}")
        entry = self.get_entry(catalog_id)
        if entry.safety_flag and not self._policy.get("require_safety_flag_for_external"):
            pass
        forbidden = self._policy.get("forbidden_write_targets", [])
        for target in forbidden:
            if str(resolved_path).endswith(target.rstrip("/")) or target.rstrip("/") in str(resolved_path):
                raise CatalogError(f"forbidden write target pattern: {target}")

    def read_json(self, catalog_id: str) -> Any:
        entry = self.get_entry(catalog_id)
        paths = entry.resolve_paths()
        if not paths:
            raise CatalogError(f"no files resolved for {catalog_id}")
        if len(paths) > 1:
            raise CatalogError(f"read_json requires single file; got {len(paths)} for {catalog_id}")
        return self._read_file(paths[0], catalog_id)

    def read_jsonl(self, catalog_id: str, limit: int | None = None) -> list[dict]:
        entry = self.get_entry(catalog_id)
        paths = entry.resolve_paths()
        if not paths:
            raise CatalogError(f"no files resolved for {catalog_id}")
        if len(paths) > 1:
            raise CatalogError(f"read_jsonl requires single file; got {len(paths)} for {catalog_id}")
        return list(self.iter_jsonl(catalog_id, limit=limit))

    def iter_jsonl(self, catalog_id: str, limit: int | None = None) -> Iterator[dict]:
        entry = self.get_entry(catalog_id)
        paths = entry.resolve_paths()
        if not paths:
            raise CatalogError(f"no files resolved for {catalog_id}")
        path = paths[0]
        self.assert_read_allowed(catalog_id, path)
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if self._policy.get("require_schema_validation", True):
                    validate_row(catalog_id, row, entry.schema_path)
                yield row
                count += 1
                if limit is not None and count >= limit:
                    break

    def _read_file(self, path: Path, catalog_id: str) -> Any:
        self.assert_read_allowed(catalog_id, path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def stat(self, catalog_id: str) -> dict:
        entry = self.get_entry(catalog_id)
        paths = entry.resolve_paths()
        if not paths:
            return {"catalog_id": catalog_id, "exists": False, "files": 0}
        total_size = sum(p.stat().st_size for p in paths if p.exists())
        mtime = max((p.stat().st_mtime for p in paths if p.exists()), default=0)
        return {
            "catalog_id": catalog_id,
            "exists": True,
            "files": len(paths),
            "total_bytes": total_size,
            "latest_mtime": mtime,
            "paths": [str(p) for p in paths[:5]],
        }


def validate_row(catalog_id: str, row: dict, schema_path: Path | None) -> None:
    """Lightweight schema validation without external jsonschema dependency."""
    if schema_path and schema_path.exists():
        schema = _load_json(schema_path)
        required = schema.get("required", [])
        for field in required:
            if field not in row:
                raise CatalogError(f"{catalog_id}: missing required field '{field}'")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            extra = set(row.keys()) - allowed
            if extra:
                raise CatalogError(f"{catalog_id}: unexpected fields {extra}")
        return

    if catalog_id == "okx.trades.weekly" or catalog_id == "etf.trades.weekly":
        _validate_trade_record(row, catalog_id)
    elif catalog_id == "okx.trade_memory.export":
        _validate_okx_trade_memory(row, catalog_id)
    elif catalog_id in (
        "pm.local.funding.unified",
        "pm.local.crypto_price_tape",
        "macro.dxy.daily",
    ):
        _validate_observation_jsonl(row, catalog_id)


def _validate_observation_jsonl(row: dict, catalog_id: str) -> None:
    if row.get("observation_only") is not True:
        raise CatalogError(f"{catalog_id}: observation_only must be true")
    if catalog_id == "pm.local.funding.unified":
        for field in ("timestamp", "exchange", "symbol", "funding_rate", "source_file"):
            if field not in row:
                raise CatalogError(f"{catalog_id}: missing '{field}'")
    elif catalog_id == "pm.local.crypto_price_tape":
        for field in ("timestamp", "market_id", "slug", "asset", "outcome", "price", "source"):
            if field not in row:
                raise CatalogError(f"{catalog_id}: missing '{field}'")
        if row.get("live") is not True:
            raise CatalogError(f"{catalog_id}: live tape requires live=true")
    elif catalog_id == "macro.dxy.daily":
        if "date" not in row and "timestamp" not in row:
            raise CatalogError(f"{catalog_id}: missing date/timestamp")
        if "close" not in row:
            raise CatalogError(f"{catalog_id}: missing close")
        if "source" not in row:
            raise CatalogError(f"{catalog_id}: missing source")


def _validate_trade_record(row: dict, catalog_id: str) -> None:
    required = (
        "source", "symbol", "strategy", "entry_time", "exit_time",
        "holding_minutes", "session", "pnl_pct", "win",
    )
    for field in required:
        if field not in row:
            raise CatalogError(f"{catalog_id}: missing '{field}'")


def _validate_okx_trade_memory(row: dict, catalog_id: str) -> None:
    required = (
        "source_project", "source_market", "symbol", "ts_open", "ts_close",
        "direction", "signal_type", "exit_reason", "hold_sec",
        "gross_pnl_bps", "net_pnl_bps", "fees_bps", "session", "metadata",
    )
    for field in required:
        if field not in row:
            raise CatalogError(f"{catalog_id}: missing '{field}'")
    meta = row.get("metadata")
    if not isinstance(meta, dict):
        raise CatalogError(f"{catalog_id}: metadata must be object")


def is_experience_path(path: str | Path) -> bool:
    s = str(path).lower()
    return any(h in s for h in _EXPERIENCE_PATH_HINTS)
