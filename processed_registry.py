"""Persistent registry of successfully processed source files.

Tracks files by source folder namespace + relative path + fingerprint
(size + mtime) so relaunch does not re-queue unchanged files.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from config import _persistent_config_dir

_REGISTRY_VERSION = 1
_VALID_RESULTS = frozenset({"encoded", "copied", "kept", "skipped"})


def _normalize_source_base(source_base: str) -> str:
    """Return a stable namespace key for a source folder."""
    if not source_base:
        return ""
    resolved = Path(source_base).resolve()
    text = os.path.normcase(str(resolved))
    return text.rstrip("\\/")


def _relative_key(source_base: str, file_path: Path | str) -> str:
    """Return a relative path key using forward slashes."""
    base = Path(source_base).resolve()
    rel = Path(file_path).resolve().relative_to(base)
    return rel.as_posix()


def _fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    return {"size": stat.st_size, "mtime_ns": mtime_ns}


def _fingerprints_match(stored: dict[str, Any], current: dict[str, int]) -> bool:
    return (
        stored.get("size") == current["size"]
        and stored.get("mtime_ns") == current["mtime_ns"]
    )


class ProcessedRegistry:
    """Load/save processed_registry.json and answer skip/mark queries."""

    def __init__(self, registry_path: Path | None = None):
        if registry_path is None:
            registry_path = _persistent_config_dir() / "processed_registry.json"
        self._path = Path(registry_path)
        self._data: dict[str, Any] = {"version": _REGISTRY_VERSION, "sources": {}}
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data = loaded
                self._data.setdefault("version", _REGISTRY_VERSION)
                self._data.setdefault("sources", {})
        except (json.JSONDecodeError, OSError):
            self._data = {"version": _REGISTRY_VERSION, "sources": {}}

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _source_entries(self, source_base: str) -> dict[str, Any]:
        key = _normalize_source_base(source_base)
        if not key:
            return {}
        sources = self._data.setdefault("sources", {})
        return sources.setdefault(key, {})

    def should_skip(self, source_base: str, file_path: Path | str) -> bool:
        """Return True if file matches a stored fingerprint (unchanged)."""
        path = Path(file_path)
        if not path.is_file():
            return False

        rel = _relative_key(source_base, path)
        entry = self._source_entries(source_base).get(rel)
        if not entry:
            return False

        try:
            current = _fingerprint(path)
        except OSError:
            return False

        return _fingerprints_match(entry, current)

    def mark_processed(
        self,
        source_base: str,
        file_path: Path | str,
        result: str,
        *,
        output_rel: str | None = None,
        source_rel: str | None = None,
    ):
        """Record a successfully handled file under source_base."""
        if result not in _VALID_RESULTS:
            raise ValueError(f"Invalid result: {result}")

        path = Path(file_path)
        if not path.is_file():
            return

        try:
            fp = _fingerprint(path)
        except OSError:
            return

        rel = _relative_key(source_base, path)
        record: dict[str, Any] = {
            **fp,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "result": result,
        }
        if output_rel:
            record["output_rel"] = output_rel
        if source_rel:
            record["source_rel"] = source_rel

        self._source_entries(source_base)[rel] = record
        self._save()

    def relative_key(self, source_base: str, file_path: Path | str) -> str:
        """Return the registry key for a path under source_base."""
        return _relative_key(source_base, file_path)

    def prune(self, source_base: str) -> int:
        """Remove entries whose files no longer exist under source_base."""
        entries = self._source_entries(source_base)
        if not entries:
            return 0

        base = Path(source_base).resolve()
        removed = 0
        for rel in list(entries.keys()):
            if not (base / rel).is_file():
                del entries[rel]
                removed += 1

        if removed:
            self._save()
        return removed

    def clear(self, source_base: str | None = None) -> int:
        """Clear all entries, or only those for one source folder."""
        sources: dict[str, Any] = self._data.setdefault("sources", {})
        if source_base is None:
            count = sum(len(v) for v in sources.values())
            sources.clear()
            self._save()
            return count

        key = _normalize_source_base(source_base)
        if key in sources:
            count = len(sources[key])
            del sources[key]
            self._save()
            return count
        return 0
