"""MongoDB client lifecycle for a long-running Gunicorn/Flask process.

Each Gunicorn worker is its own process, so each worker owns one MongoClient.
Do not create a client per request — handshake + TLS is 50–500ms.
"""

from __future__ import annotations

from flask import current_app, g
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.server_api import ServerApi

_client: MongoClient | None = None


def _build_client(uri: str) -> MongoClient:
    # Pool and timeouts assume a small Gunicorn deployment (2–4 sync workers)
    # talking to Atlas over the public internet, not a serverless function.
    return MongoClient(
        uri,
        server_api=ServerApi("1"),
        # Peak concurrent ops per worker for this search UI is low; 20 leaves
        # headroom without holding idle sockets on Atlas (~1MB RAM each).
        maxPoolSize=20,
        # One warmed socket so the first search after a quiet period is not a
        # full handshake. Keep this at 0 if workers sit idle for hours.
        minPoolSize=1,
        # Drop idle sockets before typical NAT / load-balancer idle timeouts.
        maxIdleTimeMS=60_000,
        connectTimeoutMS=10_000,
        serverSelectionTimeoutMS=5_000,
        retryWrites=True,
        appname="podcast-transcript-search",
    )


def init_db(app) -> None:
    global _client
    uri = app.config.get("MONGODB_URI")
    if not uri:
        app.logger.warning("MONGODB_URI is not set; search endpoints will fail.")
        return
    if _client is None:
        _client = _build_client(uri)

    @app.teardown_appcontext
    def _teardown(_exc):
        g.pop("mongo_db", None)


def get_client() -> MongoClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized. Set MONGODB_URI.")
    return _client


def get_db() -> Database:
    if "mongo_db" not in g:
        g.mongo_db = get_client()[current_app.config["MONGODB_DB"]]
    return g.mongo_db


def get_snippets() -> Collection:
    return get_db()[current_app.config["MONGODB_COLLECTION"]]


def ping() -> bool:
    get_client().admin.command("ping")
    return True


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
