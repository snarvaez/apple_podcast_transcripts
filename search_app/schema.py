"""Polymorphic snippet schema for podcasts, YouTube, and later assets.

One collection: each document is a bounded searchable chunk (`text`) with
source + item metadata denormalized (extended reference). Discriminator is
`source_kind`. `text` stays the Voyage auto-embed path.

Legacy podcast field names are still written as aliases so existing unique
indexes and in-flight queries keep working.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 2

SOURCE_KINDS = (
    "podcast",
    "youtube",
    "github",
    "blog",
    "social",
    "docs",
    "other",
)

# $project for search pipelines
SNIPPET_PROJECT = {
    "schema_version": 1,
    "source_kind": 1,
    "source_id": 1,
    "source_title": 1,
    "source_author": 1,
    "item_id": 1,
    "item_title": 1,
    "item_url": 1,
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
    "youtube_video_id": 1,
    "media_kind": 1,
    "start_ms": 1,
    "end_ms": 1,
    "published_at": 1,
    "chunk_index": 1,
    "text": 1,
}


def snippet_document(
    *,
    source_kind: str,
    source_id: str,
    source_title: str,
    source_author: str,
    item_id: str,
    item_title: str,
    item_url: str,
    chunk_index: int,
    text: str,
    **extra: Any,
) -> dict[str, Any]:
    kind = source_kind if source_kind in SOURCE_KINDS else "other"
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_kind": kind,
        "source_id": source_id,
        "source_title": source_title,
        "source_author": source_author,
        "item_id": item_id,
        "item_title": item_title,
        "item_url": item_url,
        "chunk_index": chunk_index,
        "text": text,
        # Aliases — same values, old query paths / unique index keys.
        "media_kind": kind,
        "podcast_id": source_id,
        "podcast_title": source_title,
        "podcast_author": source_author,
        "episode_id": item_id,
        "episode_title": item_title,
        "episode_url": item_url,
    }
    doc.update({k: v for k, v in extra.items() if v is not None})
    return doc


def coerce(doc: dict[str, Any]) -> dict[str, Any]:
    """Fill canonical fields from legacy names (and the reverse)."""
    out = dict(doc)
    kind = (
        doc.get("source_kind")
        or doc.get("media_kind")
        or ("youtube" if doc.get("youtube_video_id") else "podcast")
    )
    source_id = doc.get("source_id") or doc.get("podcast_id")
    source_title = doc.get("source_title") or doc.get("podcast_title")
    source_author = doc.get("source_author") or doc.get("podcast_author")
    item_id = doc.get("item_id") or doc.get("episode_id")
    item_title = doc.get("item_title") or doc.get("episode_title")
    item_url = doc.get("item_url") or doc.get("episode_url")
    out["source_kind"] = kind
    out["media_kind"] = kind
    out["source_id"] = source_id
    out["podcast_id"] = source_id
    out["source_title"] = source_title
    out["podcast_title"] = source_title
    out["source_author"] = source_author
    out["podcast_author"] = source_author
    out["item_id"] = item_id
    out["episode_id"] = item_id
    out["item_title"] = item_title
    out["episode_title"] = item_title
    out["item_url"] = item_url
    out["episode_url"] = item_url
    return out


MIGRATE_PIPELINE: list[dict[str, Any]] = [
    {
        "$set": {
            "schema_version": SCHEMA_VERSION,
            "source_kind": {
                "$switch": {
                    "branches": [
                        {
                            "case": {"$eq": [{"$ifNull": ["$source_kind", ""]}, "youtube"]},
                            "then": "youtube",
                        },
                        {
                            "case": {"$eq": [{"$ifNull": ["$media_kind", ""]}, "youtube"]},
                            "then": "youtube",
                        },
                        {
                            "case": {
                                "$gt": [
                                    {"$strLenCP": {"$ifNull": ["$youtube_video_id", ""]}},
                                    0,
                                ]
                            },
                            "then": "youtube",
                        },
                    ],
                    "default": {"$ifNull": ["$source_kind", "podcast"]},
                }
            },
            "source_id": {"$ifNull": ["$source_id", "$podcast_id"]},
            "source_title": {"$ifNull": ["$source_title", "$podcast_title"]},
            "source_author": {"$ifNull": ["$source_author", "$podcast_author"]},
            "item_id": {"$ifNull": ["$item_id", "$episode_id"]},
            "item_title": {"$ifNull": ["$item_title", "$episode_title"]},
            "item_url": {"$ifNull": ["$item_url", "$episode_url"]},
            "ingest_source": {"$ifNull": ["$ingest_source", "$source"]},
        }
    },
    {
        "$set": {
            "media_kind": "$source_kind",
            "podcast_id": {"$ifNull": ["$podcast_id", "$source_id"]},
            "podcast_title": {"$ifNull": ["$podcast_title", "$source_title"]},
            "podcast_author": {"$ifNull": ["$podcast_author", "$source_author"]},
            "episode_id": {"$ifNull": ["$episode_id", "$item_id"]},
            "episode_title": {"$ifNull": ["$episode_title", "$item_title"]},
            "episode_url": {"$ifNull": ["$episode_url", "$item_url"]},
        }
    },
]
