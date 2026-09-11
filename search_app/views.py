from flask import Blueprint, current_app, jsonify, render_template, request

from .db import get_snippets, ping
from .search import search_topic

bp = Blueprint("main", __name__)

SAMPLE_QUERIES = [
    "ransomware double extortion",
    "passkeys and password managers",
    "CRISPR base editing",
    "James Webb exoplanet atmospheres",
    "sticky inflation",
    "AI replacing call center jobs",
]


@bp.get("/")
def index():
    return render_template("index.html", sample_queries=SAMPLE_QUERIES)


@bp.get("/health")
def health():
    try:
        ping()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@bp.get("/api/search")
def api_search():
    query = request.args.get("q", "")
    try:
        collection = get_snippets()
        payload = search_topic(
            collection,
            query,
            search_index=current_app.config["SEARCH_INDEX"],
            vector_index=current_app.config["VECTOR_INDEX"],
            model=current_app.config["EMBEDDING_MODEL"],
            limit=current_app.config["SEARCH_LIMIT"],
            snippets_per_episode=current_app.config["SNIPPETS_PER_EPISODE"],
        )
        return jsonify(payload)
    except Exception as exc:
        current_app.logger.exception("search failed")
        return jsonify({"error": str(exc), "query": query, "podcasts": []}), 503
