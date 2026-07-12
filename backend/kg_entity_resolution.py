"""Structured, boundary-aware entity resolution for PrimeKG.

Replaces fragile substring matching (`the` -> `thecoma`) with a tiered resolver:

  1. exact normalized-name match
  2. exact alias match (via kg_aliases)
  3. case-insensitive exact match
  4. token-boundary-aware match
  5. controlled fuzzy match (only at high confidence, single candidate)
  6. unresolved / ambiguous otherwise

The scoring core (`resolve_from_candidates`) is pure and unit-testable without a
database. `resolve_mentions` wires it to a bounded, index-aware Cypher candidate
fetch. Ambiguous mentions are never silently collapsed to one entity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from backend.kg_aliases import default_registry

# Resolution outcome tiers and their base confidence.
TIER_EXACT = "exact_name"
TIER_ALIAS = "alias"
TIER_CI_EXACT = "ci_exact"
TIER_TOKEN = "token_boundary"
TIER_FUZZY = "fuzzy"
TIER_UNRESOLVED = "unresolved"
TIER_AMBIGUOUS = "ambiguous"

_TIER_CONFIDENCE = {
    TIER_EXACT: 1.0,
    TIER_ALIAS: 0.95,
    TIER_CI_EXACT: 0.9,
    TIER_TOKEN: 0.75,
}
MIN_CONFIDENCE = 0.7          # below this -> unresolved
FUZZY_MIN_RATIO = 0.9         # controlled fuzzy floor
AMBIGUITY_MARGIN = 0.05       # top-2 within this -> ambiguous
MIN_TOKEN_LEN = 4             # a token shorter than this cannot alone anchor a fuzzy/boundary match

_GREEK = {"alpha": "a", "beta": "b", "gamma": "g", "delta": "d",
          "α": "a", "β": "b", "γ": "g", "δ": "d"}

_MENTION_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on", "at",
    "is", "are", "was", "were", "be", "what", "which", "who", "how", "why",
    "does", "do", "can", "could", "would", "should", "tell", "me", "about",
    "also", "them", "they", "this", "that", "these", "those", "there", "here",
    "some", "many", "most", "common", "cause", "causes", "connected", "related",
    "through", "drug", "drugs", "disease", "diseases", "gene", "genes",
    "treat", "treats", "treatment", "mechanism", "mechanisms", "you", "your",
    "info", "information", "list", "give", "show", "explain", "one", "ones",
}


def normalize_mention(text) -> str:
    text = str(text or "").strip().lower()
    for greek, latin in _GREEK.items():
        text = text.replace(greek, latin)
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s/+-]", " ", text)          # keep word chars, /, +, -
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _singularize(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(text: str) -> list:
    return [t for t in re.split(r"[^\w]+", normalize_mention(text)) if t]


def extract_mentions(question: str, max_ngram: int = 4) -> list:
    """Boundary-aware candidate mentions: content tokens and short n-grams."""
    raw_tokens = tokens(question)
    content = [t for t in raw_tokens if t not in _MENTION_STOPWORDS and len(t) >= 3]
    mentions = []
    seen = set()

    def _add(m):
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            mentions.append(m)

    # n-grams over the *original* token stream (so multi-word names survive),
    # trimmed of leading/trailing stopwords.
    for n in range(min(max_ngram, len(raw_tokens)), 0, -1):
        for i in range(len(raw_tokens) - n + 1):
            gram = raw_tokens[i:i + n]
            while gram and gram[0] in _MENTION_STOPWORDS:
                gram = gram[1:]
            while gram and gram[-1] in _MENTION_STOPWORDS:
                gram = gram[:-1]
            if not gram:
                continue
            phrase = " ".join(gram)
            if len(phrase) >= 3 and any(len(t) >= 3 for t in gram):
                _add(phrase)
    for token in content:
        _add(token)
    # split hyphenated tokens (cgrp-related -> cgrp)
    for token in list(content):
        for part in token.split("-"):
            if len(part) >= 3 and part not in _MENTION_STOPWORDS:
                _add(part)
    return mentions


@dataclass
class Resolution:
    mention: str
    normalized: str
    resolved_id: str = ""
    resolved_name: str = ""
    entity_type: str = ""
    method: str = TIER_UNRESOLVED
    confidence: float = 0.0
    aliases_considered: list = field(default_factory=list)
    ambiguous_alternatives: list = field(default_factory=list)
    unresolved_reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.method not in (TIER_UNRESOLVED, TIER_AMBIGUOUS) and bool(self.resolved_id)

    def as_dict(self):
        return {
            "mention": self.mention, "normalized": self.normalized,
            "resolvedId": self.resolved_id, "resolvedName": self.resolved_name,
            "entityType": self.entity_type, "method": self.method,
            "confidence": round(self.confidence, 4),
            "aliasesConsidered": self.aliases_considered,
            "ambiguousAlternatives": self.ambiguous_alternatives,
            "unresolvedReason": self.unresolved_reason,
        }


def _cand_key(c):
    return c.get("id") or c.get("prime_id")


def resolve_from_candidates(mention, candidates, alias_names=None, alias_meta=None) -> Resolution:
    """Pure resolver. `candidates` = [{id,name,node_type,source}, ...]."""
    norm = normalize_mention(mention)
    res = Resolution(mention=mention, normalized=norm, aliases_considered=list(alias_names or []))
    if not norm:
        res.unresolved_reason = "empty mention"
        return res

    mention_tokens = set(_singularize(t) for t in norm.split())
    scored = []
    alias_norms = {normalize_mention(a) for a in (alias_names or [])}
    for cand in candidates or []:
        cid = _cand_key(cand)
        cname = cand.get("name") or ""
        cnorm = normalize_mention(cname)
        if not cid or not cnorm:
            continue
        if cnorm == norm:
            method, conf = TIER_EXACT, _TIER_CONFIDENCE[TIER_EXACT]
        elif cnorm in alias_norms:
            method, conf = TIER_ALIAS, _TIER_CONFIDENCE[TIER_ALIAS]
        elif cnorm.lower() == norm.lower():
            method, conf = TIER_CI_EXACT, _TIER_CONFIDENCE[TIER_CI_EXACT]
        else:
            cand_tokens = set(_singularize(t) for t in cnorm.split())
            # token-boundary: every mention token is a whole token of the name,
            # and the name isn't drastically longer (avoids hub-name dilution).
            usable = {t for t in mention_tokens if len(t) >= 3}
            if usable and usable.issubset(cand_tokens) and len(cand_tokens) <= len(usable) + 2:
                method, conf = TIER_TOKEN, _TIER_CONFIDENCE[TIER_TOKEN]
            else:
                ratio = SequenceMatcher(None, norm, cnorm).ratio()
                if ratio >= FUZZY_MIN_RATIO and len(norm) >= MIN_TOKEN_LEN:
                    method, conf = TIER_FUZZY, ratio
                else:
                    continue
        scored.append((conf, method, cand))

    if not scored:
        res.unresolved_reason = "no candidate met the confidence threshold"
        return res

    scored.sort(key=lambda item: (-item[0], len(item[2].get("name") or "")))
    best_conf, best_method, best = scored[0]

    if best_conf < MIN_CONFIDENCE:
        res.method = TIER_UNRESOLVED
        res.confidence = best_conf
        res.unresolved_reason = f"best confidence {best_conf:.2f} below {MIN_CONFIDENCE}"
        return res

    # Ambiguity: multiple distinct entities within the margin at the top tier,
    # unless the top is a unique exact match.
    contenders = [s for s in scored if best_conf - s[0] <= AMBIGUITY_MARGIN and _cand_key(s[2]) != _cand_key(best)]
    exact_unique = best_method == TIER_EXACT and not any(
        s[1] == TIER_EXACT and _cand_key(s[2]) != _cand_key(best) for s in scored)
    if contenders and not exact_unique:
        res.method = TIER_AMBIGUOUS
        res.confidence = best_conf
        res.ambiguous_alternatives = [
            {"id": _cand_key(c), "name": c.get("name"), "type": c.get("node_type"), "confidence": round(cf, 4)}
            for cf, _, c in scored[:5]
        ]
        res.unresolved_reason = "multiple candidates with similar confidence"
        return res

    res.resolved_id = _cand_key(best)
    res.resolved_name = best.get("name") or ""
    res.entity_type = best.get("node_type") or best.get("type") or ""
    res.method = best_method
    res.confidence = best_conf
    if alias_meta and alias_meta.get("ambiguous"):
        res.ambiguous_alternatives = [{"aliasNote": alias_meta.get("note")}]
    return res


# --- DB-backed candidate fetch (bounded, index-aware) -----------------------

def fetch_candidates(session, mention_norm, alias_names=None, limit=25):
    """Bounded candidate lookup using the name index; no unbounded scans/paths."""
    search_terms = list({mention_norm, *[normalize_mention(a) for a in (alias_names or [])]})
    search_terms = [t for t in search_terms if t]
    if not search_terms:
        return []
    prefixes = [t for t in search_terms if len(t) >= 4]
    rows = session.run(
        """
        MATCH (n:PrimeNode)
        WHERE NOT toLower(coalesce(n.source,'')) CONTAINS 'fake-test-only'
          AND (
            toLower(n.name) IN $terms
            OR any(t IN $prefixes WHERE toLower(n.name) STARTS WITH t)
          )
        RETURN coalesce(n.prime_id, n.id) AS id, n.name AS name,
               coalesce(n.node_type, n.type, 'other') AS node_type, n.source AS source
        ORDER BY size(n.name) ASC
        LIMIT $limit
        """,
        terms=search_terms, prefixes=prefixes, limit=int(limit),
    ).data()
    return rows


def resolve_mentions(question, session, alias_registry=None, per_mention_limit=25,
                     max_entities=12, max_mentions=16):
    """Resolve extracted mentions against the graph; return typed results.

    Mentions are capped (longer, more specific n-grams first) to bound the number
    of index lookups on large graphs.
    """
    alias_registry = alias_registry or default_registry()
    resolutions = []
    used_ids = set()
    for mention in extract_mentions(question)[:max_mentions]:
        alias_hit = alias_registry.resolve_alias(mention)
        alias_names = list(alias_hit.canonical) if alias_hit else []
        alias_meta = {"ambiguous": alias_hit.ambiguous, "note": alias_hit.note} if alias_hit else None
        candidates = fetch_candidates(session, normalize_mention(mention), alias_names, per_mention_limit)
        res = resolve_from_candidates(mention, candidates, alias_names, alias_meta)
        resolutions.append(res)

    resolved = [r for r in resolutions if r.resolved and r.resolved_id not in used_ids]
    for r in resolved:
        used_ids.add(r.resolved_id)
    ambiguous = [r for r in resolutions if r.method == TIER_AMBIGUOUS]
    unresolved = [r for r in resolutions if r.method == TIER_UNRESOLVED and len(r.normalized) >= 3]
    return {
        "resolved": resolved[:max_entities],
        "ambiguous": ambiguous,
        "unresolved": unresolved,
    }
