"""Hybrid topic search: Atlas Search (lexical) + Voyage auto-embed (semantic)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import re

from pymongo.collection import Collection
from pymongo.errors import OperationFailure, PyMongoError

LEXICAL_MAX_TIME_MS = 15_000
VECTOR_MAX_TIME_MS = 20_000
RANK_FUSION_MAX_TIME_MS = 35_000

VECTOR_CANDIDATES_MULTIPLIER = 10

# prefixLength 0 is required for first-letter typos ("gsming" vs "gaming").
# maxEdits 2 is the Atlas Search cap (Levenshtein).
FUZZY = {"maxEdits": 2, "prefixLength": 0, "maxExpansions": 50}


def lexical_pipeline(query: str, index: str, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "$search": {
                "index": index,
                "compound": {
                    "should": [
                        {"text": {"query": query, "path": "text"}},
                        {
                            "text": {
                                "query": query,
                                "path": "episode_title",
                                "score": {"boost": {"value": 2.0}},
                            }
                        },
                        {
                            "text": {
                                "query": query,
                                "path": "episode_title.fuzzy",
                                "fuzzy": FUZZY,
                                "score": {"boost": {"value": 2.2}},
                            }
                        },
                        {
                            "text": {
                                "query": query,
                                "path": "text.fuzzy",
                                "fuzzy": FUZZY,
                                "score": {"boost": {"value": 0.8}},
                            }
                        },
                    ]
                },
                "highlight": {
                    "path": ["text", "episode_title"],
                    "maxNumPassages": 2,
                },
            }
        },
        {"$limit": limit},
        {
            "$project": {
                "podcast_id": 1,
                "podcast_title": 1,
                "podcast_author": 1,
                "episode_id": 1,
                "episode_title": 1,
                "episode_url": 1,
                "audio_url": 1,
                "spotify_episode_id": 1,
                "apple_track_id": 1,
                "itunes_id": 1,
                "start_ms": 1,
                "end_ms": 1,
                "published_at": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "searchScore"},
                "highlights": {"$meta": "searchHighlights"},
            }
        },
    ]


def vector_pipeline(
    query: str, index: str, model: str, limit: int
) -> list[dict[str, Any]]:
    num_candidates = min(max(limit * VECTOR_CANDIDATES_MULTIPLIER, 40), 10_000)
    return [
        {
            "$vectorSearch": {
                "index": index,
                "path": "text",
                "query": {"text": query},
                "model": model,
                "numCandidates": num_candidates,
                "limit": limit,
            }
        },
        {
            "$project": {
                "podcast_id": 1,
                "podcast_title": 1,
                "podcast_author": 1,
                "episode_id": 1,
                "episode_title": 1,
                "episode_url": 1,
                "audio_url": 1,
                "spotify_episode_id": 1,
                "apple_track_id": 1,
                "itunes_id": 1,
                "start_ms": 1,
                "end_ms": 1,
                "published_at": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]


def rank_fusion_pipeline(
    query: str,
    *,
    search_index: str,
    vector_index: str,
    model: str,
    limit: int,
) -> list[dict[str, Any]]:
    num_candidates = min(max(limit * VECTOR_CANDIDATES_MULTIPLIER, 40), 10_000)
    return [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "vectorPipeline": [
                            {
                                "$vectorSearch": {
                                    "index": vector_index,
                                    "path": "text",
                                    "query": {"text": query},
                                    "model": model,
                                    "numCandidates": num_candidates,
                                    "limit": limit,
                                }
                            }
                        ],
                        "textPipeline": [
                            {
                                "$search": {
                                    "index": search_index,
                                    "compound": {
                                        "should": [
                                            {"text": {"query": query, "path": "text"}},
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "episode_title",
                                                    "score": {"boost": {"value": 2.0}},
                                                }
                                            },
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "episode_title.fuzzy",
                                                    "fuzzy": FUZZY,
                                                    "score": {"boost": {"value": 2.2}},
                                                }
                                            },
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "text.fuzzy",
                                                    "fuzzy": FUZZY,
                                                    "score": {"boost": {"value": 0.8}},
                                                }
                                            },
                                        ]
                                    },
                                    "highlight": {
                                        "path": ["text", "episode_title"],
                                        "maxNumPassages": 2,
                                    },
                                }
                            },
                            {"$limit": limit},
                        ],
                    }
                },
                "combination": {
                    "weights": {"vectorPipeline": 1.2, "textPipeline": 1.0}
                },
            }
        },
        {"$limit": limit},
        {
            "$project": {
                "podcast_id": 1,
                "podcast_title": 1,
                "podcast_author": 1,
                "episode_id": 1,
                "episode_title": 1,
                "episode_url": 1,
                "audio_url": 1,
                "spotify_episode_id": 1,
                "apple_track_id": 1,
                "itunes_id": 1,
                "start_ms": 1,
                "end_ms": 1,
                "published_at": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "score"},
                "highlights": {"$meta": "searchHighlights"},
            }
        },
    ]


def reciprocal_rank_fusion(
    lexical: list[dict[str, Any]],
    vector: list[dict[str, Any]],
    *,
    k: int = 60,
    lexical_weight: float = 1.0,
    vector_weight: float = 1.2,
) -> list[dict[str, Any]]:
    """RRF merge when the cluster does not support $rankFusion (needs 8.0+)."""
    scores: dict[Any, float] = defaultdict(float)
    docs: dict[Any, dict[str, Any]] = {}
    sources: dict[Any, set[str]] = defaultdict(set)

    for rank, doc in enumerate(lexical, start=1):
        doc_id = doc["_id"]
        scores[doc_id] += lexical_weight * (1.0 / (k + rank))
        docs[doc_id] = doc
        sources[doc_id].add("keyword")

    for rank, doc in enumerate(vector, start=1):
        doc_id = doc["_id"]
        scores[doc_id] += vector_weight * (1.0 / (k + rank))
        if doc_id in docs:
            if not docs[doc_id].get("highlights") and doc.get("highlights"):
                docs[doc_id]["highlights"] = doc["highlights"]
        else:
            docs[doc_id] = doc
        sources[doc_id].add("semantic")

    ranked = []
    for doc_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        merged = dict(docs[doc_id])
        merged["score"] = score
        merged["match_types"] = sorted(sources[doc_id])
        ranked.append(merged)
    return ranked


def highlight_html(highlights: list[dict[str, Any]] | None, fallback: str) -> str:
    if not highlights:
        text = fallback.strip()
        if len(text) > 420:
            text = text[:420].rsplit(" ", 1)[0] + "…"
        return _escape(text)

    passages = []
    for hl in highlights:
        parts = []
        for piece in hl.get("texts", []):
            value = _escape(piece.get("value", ""))
            if piece.get("type") == "hit":
                parts.append(f"<mark>{value}</mark>")
            else:
                parts.append(value)
        joined = "".join(parts).strip()
        if joined:
            passages.append(joined)
    return " … ".join(passages) if passages else _escape(fallback[:420])


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    published = doc.get("published_at")
    return {
        "id": str(doc.get("_id", "")),
        "podcast_id": doc.get("podcast_id"),
        "podcast_title": doc.get("podcast_title"),
        "podcast_author": doc.get("podcast_author"),
        "episode_id": doc.get("episode_id"),
        "episode_title": doc.get("episode_title"),
        "episode_url": doc.get("episode_url"),
        "audio_url": doc.get("audio_url") or "",
        "spotify_episode_id": doc.get("spotify_episode_id"),
        "apple_track_id": doc.get("apple_track_id"),
        "itunes_id": doc.get("itunes_id"),
        "start_ms": doc.get("start_ms"),
        "end_ms": doc.get("end_ms"),
        "published_at": published.isoformat() if published else None,
        "chunk_index": doc.get("chunk_index"),
        "text": doc.get("text"),
        "score": float(doc.get("score") or 0),
        "match_types": doc.get("match_types") or [],
        "snippet_html": highlight_html(doc.get("highlights"), doc.get("text") or ""),
    }


def group_by_episode(
    docs: list[dict[str, Any]], snippets_per_episode: int
) -> list[dict[str, Any]]:
    episodes: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for doc in docs:
        episode_id = doc["episode_id"]
        if episode_id not in episodes:
            order.append(episode_id)
            episodes[episode_id] = {
                "podcast_id": doc["podcast_id"],
                "podcast_title": doc["podcast_title"],
                "podcast_author": doc["podcast_author"],
                "episode_id": episode_id,
                "episode_title": doc["episode_title"],
                "episode_url": doc["episode_url"],
                "audio_url": doc.get("audio_url") or "",
                "spotify_episode_id": doc.get("spotify_episode_id"),
                "apple_track_id": doc.get("apple_track_id"),
                "itunes_id": doc.get("itunes_id"),
                "published_at": doc["published_at"],
                "score": doc["score"],
                "match_types": set(doc.get("match_types") or []),
                "snippets": [],
            }
        bucket = episodes[episode_id]
        bucket["score"] = max(bucket["score"], doc["score"])
        bucket["match_types"].update(doc.get("match_types") or [])
        if len(bucket["snippets"]) < snippets_per_episode:
            bucket["snippets"].append(
                {
                    "chunk_index": doc["chunk_index"],
                    "snippet_html": doc["snippet_html"],
                    "score": doc["score"],
                    "match_types": doc.get("match_types") or [],
                    "start_ms": doc.get("start_ms"),
                    "end_ms": doc.get("end_ms"),
                    "audio_url": doc.get("audio_url") or "",
                }
            )

    grouped_podcasts: dict[str, dict[str, Any]] = {}
    podcast_order: list[str] = []
    for episode_id in order:
        episode = episodes[episode_id]
        episode["match_types"] = sorted(episode["match_types"])
        podcast_id = episode["podcast_id"]
        if podcast_id not in grouped_podcasts:
            podcast_order.append(podcast_id)
            grouped_podcasts[podcast_id] = {
                "podcast_id": podcast_id,
                "podcast_title": episode["podcast_title"],
                "podcast_author": episode["podcast_author"],
                "score": episode["score"],
                "episodes": [],
            }
        show = grouped_podcasts[podcast_id]
        show["score"] = max(show["score"], episode["score"])
        show["episodes"].append(episode)

    return [grouped_podcasts[pid] for pid in podcast_order]


def _annotate_match_types(
    docs: list[dict[str, Any]], lexical_ids: set[Any], vector_ids: set[Any]
) -> None:
    for doc in docs:
        types = []
        if doc["_id"] in lexical_ids:
            types.append("keyword")
        if vector_ids:
            if doc["_id"] in vector_ids:
                types.append("semantic")
        elif doc["_id"] not in lexical_ids:
            types.append("semantic")
        doc["match_types"] = types


def _run_aggregate(collection: Collection, pipeline: list[dict[str, Any]], max_time_ms: int):
    return list(collection.aggregate(pipeline, maxTimeMS=max_time_ms))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            ins, delete, sub = curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            curr.append(min(ins, delete, sub))
        prev = curr
    return prev[-1]


def regex_fallback(
    collection: Collection, query: str, limit: int
) -> list[dict[str, Any]]:
    """Last resort when Atlas Search / mongot is unreachable."""
    pattern = re.compile(re.escape(query), re.I)
    docs = list(
        collection.find(
            {
                "$or": [
                    {"episode_title": pattern},
                    {"text": pattern},
                ]
            },
            {
                "podcast_id": 1,
                "podcast_title": 1,
                "podcast_author": 1,
                "episode_id": 1,
                "episode_title": 1,
                "episode_url": 1,
                "audio_url": 1,
                "spotify_episode_id": 1,
                "apple_track_id": 1,
                "itunes_id": 1,
                "start_ms": 1,
                "end_ms": 1,
                "published_at": 1,
                "chunk_index": 1,
                "text": 1,
            },
        ).limit(limit)
    )
    for doc in docs:
        doc["score"] = 1.0
        doc["match_types"] = ["keyword"]
        text = doc.get("text") or ""
        marked = pattern.sub(lambda m: f"<mark>{_escape(m.group(0))}</mark>", text)
        if "<mark>" not in marked:
            marked = _escape(text[:420])
        elif len(marked) > 800:
            idx = marked.find("<mark>")
            start = max(0, idx - 120)
            marked = ("…" if start else "") + marked[start : start + 600]
        doc["highlights"] = None
        doc["snippet_html"] = marked
    if docs:
        return docs

    token = query.strip().lower()
    if not (token.isalpha() and 4 <= len(token) <= 16):
        return []
    # Title-only, 1 edit: "gsming"→"gaming" without matching "giving".
    scanned = collection.find(
        {},
        {
            "podcast_id": 1,
            "podcast_title": 1,
            "podcast_author": 1,
            "episode_id": 1,
            "episode_title": 1,
            "episode_url": 1,
            "audio_url": 1,
            "spotify_episode_id": 1,
            "apple_track_id": 1,
            "itunes_id": 1,
            "start_ms": 1,
            "end_ms": 1,
            "published_at": 1,
            "chunk_index": 1,
            "text": 1,
        },
    )
    fuzzy_docs: list[dict[str, Any]] = []
    seen_episodes: set[str] = set()
    for doc in scanned:
        title = (doc.get("episode_title") or "").lower()
        words = re.findall(r"[a-z0-9']+", title)
        if any(
            abs(len(token) - len(w)) <= 1 and levenshtein(token, w) == 1
            for w in words
        ):
            eid = doc.get("episode_id")
            if eid in seen_episodes:
                continue
            seen_episodes.add(eid)
            doc["score"] = 0.5
            doc["match_types"] = ["keyword"]
            doc["highlights"] = None
            doc["snippet_html"] = _escape((doc.get("text") or "")[:420])
            fuzzy_docs.append(doc)
            if len(fuzzy_docs) >= limit:
                break
    return fuzzy_docs


def search_topic(
    collection: Collection,
    query: str,
    *,
    search_index: str,
    vector_index: str,
    model: str,
    limit: int,
    snippets_per_episode: int,
) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"query": query, "mode": None, "podcasts": [], "total_snippets": 0}

    lexical_docs: list[dict[str, Any]] = []
    vector_docs: list[dict[str, Any]] = []
    warnings: list[str] = []
    ranked: list[dict[str, Any]] = []
    mode: str | None = None

    try:
        fused = _run_aggregate(
            collection,
            rank_fusion_pipeline(
                query,
                search_index=search_index,
                vector_index=vector_index,
                model=model,
                limit=limit,
            ),
            RANK_FUSION_MAX_TIME_MS,
        )
        if fused:
            for doc in fused:
                doc["match_types"] = ["keyword", "semantic"]
            ranked = fused
            mode = "rankFusion"
    except (PyMongoError, OperationFailure) as exc:
        warnings.append(f"$rankFusion unavailable ({exc}); combining pipelines.")

    if not ranked:
        try:
            lexical_docs = _run_aggregate(
                collection,
                lexical_pipeline(query, search_index, limit),
                LEXICAL_MAX_TIME_MS,
            )
        except (PyMongoError, OperationFailure) as exc:
            warnings.append(f"Atlas Search unavailable: {exc}")
        try:
            vector_docs = _run_aggregate(
                collection,
                vector_pipeline(query, vector_index, model, limit),
                VECTOR_MAX_TIME_MS,
            )
        except (PyMongoError, OperationFailure) as exc:
            warnings.append(f"Vector search unavailable: {exc}")
        used_fallback = False
        if not lexical_docs:
            fallback_docs = regex_fallback(collection, query, limit)
            if fallback_docs:
                lexical_docs = fallback_docs
                used_fallback = True
                warnings.append("No Atlas Search hits; used title/text match.")
        ranked = reciprocal_rank_fusion(lexical_docs, vector_docs)
        if lexical_docs and vector_docs:
            mode = "rrf"
        elif used_fallback:
            mode = "fallback"
        elif lexical_docs:
            mode = "keyword"
        elif vector_docs:
            mode = "semantic"
        else:
            mode = None

    serialized = []
    for doc in ranked:
        item = _serialize(doc)
        if doc.get("snippet_html") and not (doc.get("highlights")):
            item["snippet_html"] = doc["snippet_html"]
        serialized.append(item)
    podcasts = group_by_episode(serialized, snippets_per_episode)
    return {
        "query": query,
        "mode": mode,
        "podcasts": podcasts,
        "total_snippets": len(serialized),
        "warnings": warnings,
    }
