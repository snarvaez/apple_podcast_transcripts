# Apple Podcast transcripts

Two pieces live in this repo:

1. `podcast_transcripts.py` — download / transcribe Apple Podcast episodes when a transcript exists.
2. **Transcript Search** — a Flask + PyMongo app that stores test transcripts in MongoDB Atlas, indexes them with Atlas Search and Voyage AI auto-embeddings, and lets you search by topic.

## Transcript Search

Stack: **Flask**, **PyMongo**, **Jinja2 / HTML / jQuery**, **Gunicorn + Nginx**, **MongoDB Atlas**.

Search is hybrid:

- **Keyword:** Atlas Search on `text`, `episode_title`, and `podcast_title` (English analyzer, fuzzy, highlights).
- **Semantic:** MongoDB Vector Search `autoEmbed` on `text` with the Voyage AI `voyage-4` model. Atlas generates embeddings at index time and again at query time, so the app never stores vectors or calls Voyage directly.

### Data model

Episode transcripts are unbounded, so they are **not** stored as a growing array on a podcast document (that would blow past the 16MB BSON limit and wreck the working set). Each searchable passage is its own small document in `Podcasts.transcripts`, with podcast and episode fields denormalized so a search hit does not need `$lookup`.

```json
{
  "podcast_id": "security-now",
  "podcast_title": "Security Now",
  "podcast_author": "Steve Gibson",
  "episode_id": "sn-1043",
  "episode_title": "Double Extortion Hits Regional Hospitals",
  "episode_url": "https://twit.tv/shows/security-now",
  "published_at": { "$date": "2025-03-18T00:00:00Z" },
  "chunk_index": 0,
  "text": "Ransomware crews no longer just encrypt file servers..."
}
```

Indexes:

| Name | Type | Purpose |
|------|------|---------|
| `transcript_search_index` | Atlas Search | Lexical search + highlighting |
| `transcript_vector_index` | Vector Search `autoEmbed` | Voyage `voyage-4` embeddings on `text` |
| `episode_chunk` | Classic unique | Idempotent seeding |
| `podcast_published` | Classic | Listing by show |

### Setup

Atlas needs Vector Search (automated embeddings is a preview feature on Atlas). Use a database user and allow your IP under Network Access.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set MONGODB_URI
```

Seed test transcripts **before** the first index build when you can — Automated Embedding’s initial sync is faster on a prepopulated collection:

```bash
python -m search_app.seed
```

Dev server:

```bash
flask --app wsgi:app run --debug --port 5000
```

Open http://127.0.0.1:5000 and search for topics such as `ransomware`, `CRISPR`, `sticky inflation`, or `passkeys`. Matching podcasts are grouped with the transcript passages that hit.

Health check: `GET /health`. Search API: `GET /api/search?q=ransomware`.

### Gunicorn + Nginx

```bash
gunicorn --config gunicorn.conf.py wsgi:app
```

Gunicorn binds `127.0.0.1:8000`. `deploy/nginx.conf` reverse-proxies port 80 to that process; `deploy/podcast-search.service` is a systemd unit. Point `EnvironmentFile` and `WorkingDirectory` at the deploy path and keep `MONGODB_URI` in `.env` (never in git).

Each Gunicorn worker process owns one `MongoClient` (created after fork; `preload_app = False`). Pool settings are in `search_app/db.py`.

### Ingest The MongoDB Podcast

```bash
python -m search_app.ingest
```

Pulls the RSS feed for [The MongoDB Podcast](https://podcasts.apple.com/us/podcast/the-mongodb-podcast/id1500452446) and stores Spotify `podcast:transcript` SRT files as chunked documents. Episodes without an SRT can be transcribed on Apple Silicon (ffmpeg + mlx-whisper):

```bash
python -m search_app.ingest --transcribe
```

### Tests that do not need Atlas

```bash
python -m pytest tests/test_search.py
```

---

The original downloader still expects `pip install requests feedparser` (and Whisper / ffmpeg if you transcribe audio). Transcript availability varies by show.
