"""Revisit every snippet document and refresh classic + search + vector indexes."""

from __future__ import annotations

import sys

from pymongo.server_api import ServerApi
from pymongo import MongoClient

from .config import Config
from .indexes import (
    SEARCH_INDEX_NAME,
    VECTOR_INDEX_NAME,
    ensure_classic_indexes,
    ensure_search_indexes,
    wait_for_indexes,
)
from .schema import MIGRATE_PIPELINE, SCHEMA_VERSION


def main() -> int:
    if not Config.MONGODB_URI:
        print("Set MONGODB_URI", file=sys.stderr)
        return 1
    client = MongoClient(
        Config.MONGODB_URI,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=30_000,
        socketTimeoutMS=120_000,
        appname="schema-migrate-v2",
    )
    try:
        coll = client[Config.MONGODB_DB][Config.MONGODB_COLLECTION]
        total = coll.estimated_document_count()
        print(f"Migrating {total} documents in {coll.full_name} to schema_version={SCHEMA_VERSION}")
        result = coll.update_many({}, MIGRATE_PIPELINE)
        print(
            f"matched={result.matched_count} modified={result.modified_count}"
        )
        sample = coll.find_one(
            {"schema_version": SCHEMA_VERSION},
            {
                "source_kind": 1,
                "source_id": 1,
                "item_id": 1,
                "item_title": 1,
                "text": 1,
            },
        )
        print("sample", {k: sample.get(k) for k in (sample or {}) if k != "text"})
        kinds = list(
            coll.aggregate(
                [{"$group": {"_id": "$source_kind", "n": {"$sum": 1}}}]
            )
        )
        print("source_kind counts", kinds)

        print("Ensuring classic indexes…")
        ensure_classic_indexes(coll)
        print("Updating Atlas Search + vector index definitions…")
        ensure_search_indexes(
            coll,
            vector_name=Config.VECTOR_INDEX or VECTOR_INDEX_NAME,
            search_name=Config.SEARCH_INDEX or SEARCH_INDEX_NAME,
        )
        print("Waiting until search indexes are queryable…")
        wait_for_indexes(
            coll,
            [Config.SEARCH_INDEX, Config.VECTOR_INDEX],
            timeout_seconds=300,
        )
        print("Classic indexes:", [idx["name"] for idx in coll.list_indexes()])
        for idx in coll.list_search_indexes():
            print(
                " search",
                idx.get("name"),
                idx.get("status"),
                "queryable",
                idx.get("queryable"),
            )
        print("Done.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
