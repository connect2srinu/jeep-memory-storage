from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from app.shared_memory.models import PreferenceScope


class PreferenceValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    key: str
    value_type: str
    owner_domain: str
    description: str
    canonical: bool
    sensitivity: str
    scopes: tuple[PreferenceScope, ...]
    schema_version: str
    allowed_readers: tuple[str, ...]
    allowed_writers: tuple[str, ...]
    resolution_policy: str
    allowed_values: tuple[Any, ...] = ()
    ttl_seconds: int | None = None
    aliases: tuple[str, ...] = ()


class PreferenceCatalog:
    """In-process catalog with a replaceable configuration source."""

    def __init__(self, entries: dict[str, CatalogEntry], version: str = "1") -> None:
        self.entries = entries
        self.version = version
        self._aliases = {
            alias: entry.key for entry in entries.values() for alias in entry.aliases
        }

    @classmethod
    def default(cls) -> PreferenceCatalog:
        path = files("app.shared_memory.catalog").joinpath("catalog.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = {
            key: CatalogEntry(
                key=key,
                value_type=item["type"],
                owner_domain=item["owner_domain"],
                description=item["description"],
                canonical=bool(item.get("canonical", True)),
                sensitivity=item.get("sensitivity", "normal"),
                scopes=tuple(PreferenceScope(scope) for scope in item.get("scopes", [])),
                schema_version=str(item.get("schema_version", "1")),
                allowed_readers=tuple(item.get("allowed_readers", [])),
                allowed_writers=tuple(item.get("allowed_writers", [])),
                resolution_policy=item.get("resolution_policy", key.rsplit(".", 1)[-1]),
                allowed_values=tuple(item.get("allowed_values", [])),
                ttl_seconds=item.get("ttl_seconds"),
                aliases=tuple(item.get("aliases", [])),
            )
            for key, item in payload["preferences"].items()
        }
        return cls(entries, str(payload.get("version", "1")))

    def lookup(self, key: str, proposed_domain: str | None = None) -> CatalogEntry | None:
        if key in self.entries:
            return self.entries[key]
        aliased = self._aliases.get(key)
        if aliased:
            return self.entries[aliased]
        if proposed_domain:
            return self.entries.get(f"{proposed_domain}.{key}")
        return None

    def canonicalize(self, key: str, proposed_domain: str) -> tuple[str, str, bool]:
        entry = self.lookup(key, proposed_domain)
        if entry:
            return entry.key, entry.owner_domain, True
        dynamic_key = key if "." in key else f"{proposed_domain}.{key}"
        owner_domain = dynamic_key.split(".", 1)[0]
        return dynamic_key, owner_domain, False

    def logical_key(self, key: str, owner_domain: str) -> str:
        entry = self.lookup(key, owner_domain)
        return entry.resolution_policy if entry else key.rsplit(".", 1)[-1]

    def validate_value(self, entry: CatalogEntry | None, value: Any) -> Any:
        if entry is None:
            if isinstance(value, (str, bool, int, float)) or value is None:
                return value
            raise PreferenceValidationError("dynamic preference values must be JSON scalars")
        expected = entry.value_type
        valid = {
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        }.get(expected, False)
        if not valid:
            raise PreferenceValidationError(f"{entry.key} requires value type {expected}")
        if entry.allowed_values and value not in entry.allowed_values:
            raise PreferenceValidationError(f"{entry.key} value is not in allowed_values")
        return value

    def validate_scope(self, entry: CatalogEntry | None, scope: PreferenceScope) -> None:
        if entry is not None and scope not in entry.scopes:
            raise PreferenceValidationError(f"{entry.key} does not allow {scope.value} scope")

