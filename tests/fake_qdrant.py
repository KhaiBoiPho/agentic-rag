"""An in-memory Qdrant that honours payload filters.

Deletion tests are worthless if they only assert "delete was called with a
filter that looks right" — that is the same reasoning that produced the
4.060-orphan incident, where every layer looked correct in isolation and the
cascade simply stopped at the store boundary. What has to be proven is the
end state: after the delete, a search returns nothing.

So this double stores real points and implements the subset of Qdrant's filter
language the app actually uses (`must` of `FieldCondition` with `MatchValue` /
`MatchAny`, `IsEmptyCondition`, and a nested `should`). Points go in through
the same `upsert_chunks` the ingest pipeline calls, and come out through the
same `search` the retriever calls.

Not a substitute for running against a real Qdrant — `tests/test_deletion_
integration.py` also carries a live-server test that runs when one is
reachable. This is what keeps the guarantee under test on every commit.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _payload_get(payload: dict, key: str) -> Any:
    """Resolve a dotted key like `metadata.region` against a payload."""
    cur: Any = payload
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _matches(payload: dict, condition: Any) -> bool:
    """True if `payload` satisfies one Qdrant condition."""
    # Filter (nested — the region OR-no-region clause is one of these)
    if hasattr(condition, "must") or hasattr(condition, "should"):
        must = getattr(condition, "must", None) or []
        should = getattr(condition, "should", None) or []
        if must and not all(_matches(payload, c) for c in must):
            return False
        if should and not any(_matches(payload, c) for c in should):
            return False
        return True

    # IsEmptyCondition
    is_empty = getattr(condition, "is_empty", None)
    if is_empty is not None:
        return not _payload_get(payload, is_empty.key)

    # FieldCondition
    key = getattr(condition, "key", None)
    if key is None:
        return True
    value = _payload_get(payload, key)
    match = getattr(condition, "match", None)
    if match is None:
        return True
    if getattr(match, "any", None) is not None:
        return value in match.any
    return value == getattr(match, "value", None)


class FakeQdrantClient:
    """Stores points; applies filters on search and delete."""

    def __init__(self) -> None:
        self.points: dict[Any, dict] = {}  # id -> {payload, vector}
        self.collections: set[str] = set()

    # ── collection lifecycle ────────────────────────────────────────────────
    async def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    async def create_collection(self, collection_name, **kw):
        self.collections.add(collection_name)

    async def update_collection(self, collection_name, **kw):
        return None

    async def get_collection(self, collection_name):
        return SimpleNamespace(points_count=len(self.points))

    # ── writes ──────────────────────────────────────────────────────────────
    async def upsert(self, collection_name, points, wait=True):
        for p in points:
            self.points[p.id] = {"payload": p.payload, "vector": p.vector}

    async def update_vectors(self, collection_name, points):
        for p in points:
            pid = p["id"] if isinstance(p, dict) else p.id
            vec = p["vector"] if isinstance(p, dict) else p.vector
            if pid in self.points:
                self.points[pid]["vector"].update(vec)

    async def delete(self, collection_name, points_selector):
        doomed = [
            pid for pid, rec in self.points.items() if _matches(rec["payload"], points_selector)
        ]
        for pid in doomed:
            del self.points[pid]

    # ── reads ───────────────────────────────────────────────────────────────
    async def query_points(self, collection_name, **kw):
        """Every point passing the filter, as ScoredPoint-shaped objects.

        Ranking is irrelevant to a deletion test — what matters is whether a
        payload is REACHABLE at all — so this returns matches in insertion
        order with a constant score.
        """
        query_filter = kw.get("query_filter")
        prefetch = kw.get("prefetch") or []
        if query_filter is None and prefetch:
            query_filter = getattr(prefetch[0], "filter", None)

        hits = [
            SimpleNamespace(id=pid, score=0.9, payload=rec["payload"], vector=None)
            for pid, rec in self.points.items()
            if query_filter is None or _matches(rec["payload"], query_filter)
        ]
        return SimpleNamespace(points=hits[: kw.get("limit", 10)])

    async def scroll(self, collection_name, limit=64, offset=None, **kw):
        items = [
            SimpleNamespace(id=pid, payload=rec["payload"])
            for pid, rec in list(self.points.items())
        ]
        start = offset or 0
        page = items[start : start + limit]
        next_offset = start + limit if start + limit < len(items) else None
        return page, next_offset
