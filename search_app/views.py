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


@bp.get("/listen")
def listen():
    return render_template("listen.html")


@bp.get("/api/clip")
def api_clip():
    episode_id = (request.args.get("episode") or "").strip()
    if not episode_id:
        return jsonify({"error": "episode is required"}), 400
    try:
        doc = get_snippets().find_one(
            {"episode_id": episode_id},
            {
                "audio_url": 1,
                "episode_title": 1,
                "item_title": 1,
                "podcast_title": 1,
                "source_title": 1,
                "podcast_author": 1,
                "source_author": 1,
                "episode_url": 1,
                "item_url": 1,
                "spotify_episode_id": 1,
                "apple_track_id": 1,
                "itunes_id": 1,
                "youtube_video_id": 1,
                "source_kind": 1,
            },
        )
    except Exception as exc:
        current_app.logger.exception("clip lookup failed")
        return jsonify({"error": str(exc)}), 503
    if not doc:
        return jsonify({"error": "episode not found"}), 404
    return jsonify(
        {
            "episode_id": episode_id,
            "audio_url": doc.get("audio_url") or "",
            "episode_title": doc.get("item_title") or doc.get("episode_title"),
            "item_title": doc.get("item_title") or doc.get("episode_title"),
            "podcast_title": doc.get("source_title") or doc.get("podcast_title"),
            "source_title": doc.get("source_title") or doc.get("podcast_title"),
            "podcast_author": doc.get("source_author") or doc.get("podcast_author"),
            "episode_url": doc.get("item_url") or doc.get("episode_url"),
            "item_url": doc.get("item_url") or doc.get("episode_url"),
            "spotify_episode_id": doc.get("spotify_episode_id"),
            "apple_track_id": doc.get("apple_track_id"),
            "itunes_id": doc.get("itunes_id"),
        }
    )


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
