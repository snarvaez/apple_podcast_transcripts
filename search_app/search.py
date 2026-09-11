"""Hybrid topic search: Atlas Search (lexical) + Voyage auto-embed (semantic)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pymongo.collection import Collection
from pymongo.errors import OperationFailure, PyMongoError

VECTOR_CANDIDATES_MULTIPLIER = 20


def lexical_pipeline(query: str, index: str, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "$search": {
                "index": index,
                "compound": {
                    "should": [
                        {
                            "text": {
                                "query": query,
                                "path": "text",
                                "fuzzy": {"maxEdits": 1, "prefixLength": 2},
                            }
                        },
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
                                "path": "podcast_title",
                                "score": {"boost": {"value": 1.4}},
                            }
                        },
                    ]
                },
                "highlight": {
                    "path": "text",
                    "maxNumPassages": 3,
                    "maxCharsToExamine": 200_000,
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
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "text",
                                                    "fuzzy": {
                                                        "maxEdits": 1,
                                                        "prefixLength": 2,
                                                    },
                                                }
                                            },
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "episode_title",
                                                    "score": {
                                                        "boost": {"value": 2.0}
                                                    },
                                                }
                                            },
                                            {
                                                "text": {
                                                    "query": query,
                                                    "path": "podcast_title",
                                                    "score": {
                                                        "boost": {"value": 1.4}
                                                    },
                                                }
                                            },
                                        ]
                                    },
                                    "highlight": {
                                        "path": "text",
                                        "maxNumPassages": 3,
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
    mode = "rankFusion"
    warnings: list[str] = []

    try:
        fused = list(
            collection.aggregate(
                rank_fusion_pipeline(
                    query,
                    search_index=search_index,
                    vector_index=vector_index,
                    model=model,
                    limit=limit,
                )
            )
        )
        lexical_ids = {doc["_id"] for doc in fused if doc.get("highlights")}
        if len(lexical_ids) < min(3, len(fused)):
            lexical_docs = list(
                collection.aggregate(lexical_pipeline(query, search_index, limit))
            )
            highlight_by_id = {
                doc["_id"]: doc.get("highlights") for doc in lexical_docs
            }
            lexical_ids = set(highlight_by_id)
            for doc in fused:
                if not doc.get("highlights"):
                    doc["highlights"] = highlight_by_id.get(doc["_id"])
        _annotate_match_types(fused, lexical_ids, set())
        ranked = fused
    except OperationFailure as exc:
        warnings.append(f"$rankFusion unavailable ({exc.code}); using application RRF.")
        mode = "rrf"
        try:
            lexical_docs = list(
                collection.aggregate(lexical_pipeline(query, search_index, limit))
            )
        except PyMongoError as lex_exc:
            warnings.append(f"Atlas Search query failed: {lex_exc}")
        try:
            vector_docs = list(
                collection.aggregate(
                    vector_pipeline(query, vector_index, model, limit)
                )
            )
        except PyMongoError as vec_exc:
            warnings.append(f"Vector search query failed: {vec_exc}")
        ranked = reciprocal_rank_fusion(lexical_docs, vector_docs)

    serialized = [_serialize(doc) for doc in ranked]
    podcasts = group_by_episode(serialized, snippets_per_episode)
    return {
        "query": query,
        "mode": mode,
        "podcasts": podcasts,
        "total_snippets": len(serialized),
        "warnings": warnings,
    }
