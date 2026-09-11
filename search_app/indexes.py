"""Atlas Search + Voyage auto-embed index definitions.

Create documents first, then these indexes. Automated Embedding is faster on a
prepopulated collection because the initial sync uses a higher-throughput path.
"""

from __future__ import annotations

import time
from typing import Any

from pymongo.collection import Collection
from pymongo.operations import SearchIndexModel

VECTOR_INDEX_NAME = "podcast_vector_index"
SEARCH_INDEX_NAME = "podcast_search_index"
EMBEDDING_MODEL = "voyage-4"

SNIPPET_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "podcast_id",
            "podcast_title",
            "episode_id",
            "episode_title",
            "chunk_index",
            "text",
        ],
        "properties": {
            "podcast_id": {"bsonType": "string", "minLength": 1},
            "podcast_title": {"bsonType": "string", "minLength": 1},
            "podcast_author": {"bsonType": "string"},
            "episode_id": {"bsonType": "string", "minLength": 1},
            "episode_title": {"bsonType": "string", "minLength": 1},
            "episode_url": {"bsonType": "string"},
            "published_at": {"bsonType": "date"},
            "chunk_index": {"bsonType": ["int", "long"], "minimum": 0},
            "text": {
                "bsonType": "string",
                "minLength": 1,
                "maxLength": 8000,
                "description": "Bounded transcript passage for search and auto-embed.",
            },
        },
    }
}

VECTOR_INDEX_DEFINITION: dict[str, Any] = {
    "fields": [
        {
            "type": "autoEmbed",
            "path": "text",
            "model": EMBEDDING_MODEL,
            "modality": "text",
        },
        {"type": "filter", "path": "podcast_id"},
        {"type": "filter", "path": "episode_id"},
    ]
}

def _string_with_fuzzy(analyzer: str = "lucene.english") -> dict[str, Any]:
    # lucene.english stems ("gaming" → "game"), which blocks typos like
    # "gsming". The `fuzzy` multi uses lucene.standard so $search fuzzy
    # (maxEdits 1–2) can match the raw token.
    return {
        "type": "string",
        "analyzer": analyzer,
        "multi": {
            "fuzzy": {
                "type": "string",
                "analyzer": "lucene.standard",
            }
        },
    }


SEARCH_INDEX_DEFINITION: dict[str, Any] = {
    "analyzer": "lucene.english",
    "searchAnalyzer": "lucene.english",
    "mappings": {
        "dynamic": False,
        "fields": {
            "text": _string_with_fuzzy(),
            "episode_title": _string_with_fuzzy(),
            "podcast_title": _string_with_fuzzy(),
            "podcast_id": {"type": "token"},
            "episode_id": {"type": "token"},
        },
    },
}


def ensure_collection(db, name: str) -> Collection:
    if name not in db.list_collection_names():
        db.create_collection(
            name,
            validator=SNIPPET_VALIDATOR,
            validationLevel="strict",
            validationAction="error",
        )
    return db[name]


def ensure_classic_indexes(collection: Collection) -> None:
    collection.create_index(
        [("episode_id", 1), ("chunk_index", 1)],
        unique=True,
        name="episode_chunk",
    )
    collection.create_index(
        [("podcast_id", 1), ("published_at", -1)],
        name="podcast_published",
    )


def _existing_search_names(collection: Collection) -> set[str] | None:
    try:
        return {idx["name"] for idx in collection.list_search_indexes()}
    except Exception:
        return None


def ensure_search_indexes(
    collection: Collection,
    *,
    vector_name: str = VECTOR_INDEX_NAME,
    search_name: str = SEARCH_INDEX_NAME,
    attempts: int = 6,
) -> None:
    models = {
        vector_name: SearchIndexModel(
            definition=VECTOR_INDEX_DEFINITION,
            name=vector_name,
            type="vectorSearch",
        ),
        search_name: SearchIndexModel(
            definition=SEARCH_INDEX_DEFINITION,
            name=search_name,
            type="search",
        ),
    }
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            existing = _existing_search_names(collection) or set()
            pending = [model for name, model in models.items() if name not in existing]
            if pending:
                collection.create_search_indexes(pending)
            if search_name in existing:
                collection.update_search_index(search_name, SEARCH_INDEX_DEFINITION)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(min(10 * attempt, 30))
    if last_error:
        raise last_error


def wait_for_indexes(
    collection: Collection,
    names: list[str],
    timeout_seconds: int = 300,
) -> None:
    deadline = time.time() + timeout_seconds
    pending = set(names)
    while pending and time.time() < deadline:
        status = {idx["name"]: idx for idx in collection.list_search_indexes()}
        ready = set()
        for name in pending:
            idx = status.get(name)
            if not idx:
                continue
            if idx.get("queryable") or idx.get("status") == "READY":
                ready.add(name)
        pending -= ready
        if pending:
            time.sleep(5)
    if pending:
        raise TimeoutError(f"Search indexes not queryable: {sorted(pending)}")
