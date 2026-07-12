"""Extensible biomedical alias resolution layer.

Replaces per-question hard-coded synonym dicts with a versioned provider system.
Each alias carries provenance and can flag ambiguity. Alias coverage is NOT
claimed to be complete; unresolved abbreviations are reported as unresolved,
never guessed.

Add new sources by implementing ``AliasProvider`` and registering it in
``default_registry()`` (e.g. an HGNC gene-symbol file, a DrugBank brand->generic
table). The interface returns canonical PrimeKG *names*; the entity resolver then
matches those names against the graph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIAS_FILE = ROOT / "data" / "primekg" / "kg_aliases.json"


def _norm(text) -> str:
    return " ".join(str(text or "").strip().lower().replace("_", " ").split())


@dataclass(frozen=True)
class AliasHit:
    alias: str
    canonical: tuple           # one or more canonical PrimeKG names
    entity_type: str
    source: str
    ambiguous: bool = False
    note: str = ""


class AliasProvider:
    """Interface for an alias source."""

    name = "base"

    def lookup(self, mention_norm: str) -> AliasHit | None:  # pragma: no cover - interface
        raise NotImplementedError


class JsonAliasProvider(AliasProvider):
    name = "json-curated"

    def __init__(self, path=None):
        self.path = Path(path or DEFAULT_ALIAS_FILE)
        self._by_alias: dict[str, AliasHit] = {}
        self._collisions: list[dict] = []
        self._version = 0
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._version = payload.get("version", 0)
        for entry in payload.get("aliases", []):
            alias = _norm(entry.get("alias"))
            canonical = tuple(c for c in (entry.get("canonical") or []) if c)
            if not alias or not canonical:
                continue
            ambiguous = bool(entry.get("ambiguous_note")) or len(canonical) > 1
            hit = AliasHit(
                alias=alias,
                canonical=canonical,
                entity_type=entry.get("type") or "",
                source=entry.get("source") or self.name,
                ambiguous=ambiguous,
                note=entry.get("ambiguous_note") or entry.get("note") or "",
            )
            if alias in self._by_alias and self._by_alias[alias].canonical != canonical:
                self._collisions.append({"alias": alias,
                                         "existing": list(self._by_alias[alias].canonical),
                                         "incoming": list(canonical)})
            self._by_alias[alias] = hit

    def lookup(self, mention_norm: str) -> AliasHit | None:
        return self._by_alias.get(mention_norm)

    @property
    def version(self):
        return self._version

    @property
    def collisions(self):
        return list(self._collisions)


class AliasRegistry:
    def __init__(self, providers=None):
        self.providers = providers or []

    def resolve_alias(self, mention: str) -> AliasHit | None:
        norm = _norm(mention)
        if not norm:
            return None
        for provider in self.providers:
            hit = provider.lookup(norm)
            if hit:
                return hit
        return None

    def all_collisions(self):
        out = []
        for provider in self.providers:
            out.extend(getattr(provider, "collisions", []))
        return out


_DEFAULT_REGISTRY: AliasRegistry | None = None


def default_registry() -> AliasRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = AliasRegistry([JsonAliasProvider()])
    return _DEFAULT_REGISTRY
