from search_app.chunking import chunk_cues, chunk_transcript
from search_app.srt import Cue, parse_srt_cues, srt_to_text
from search_app.share import (
    apple_listen_url,
    primary_share_url,
    spotify_episode_id_from_transcript_url,
    spotify_listen_url,
)
from search_app.search import (
    FUZZY,
    group_by_episode,
    highlight_html,
    lexical_pipeline,
    levenshtein,
    rank_fusion_pipeline,
    reciprocal_rank_fusion,
)
from search_app.transcripts import SNIPPETS


def test_spotify_and_apple_timestamp_urls():
    assert (
        spotify_listen_url("0T15bGPizAqgJgQA3rnsv4", 11120)
        == "https://open.spotify.com/episode/0T15bGPizAqgJgQA3rnsv4?t=11"
    )
    apple = apple_listen_url("1000771353400", 64000)
    assert "i=1000771353400" in apple
    assert apple.endswith("t=64") or "&t=64" in apple
    assert primary_share_url(
        {"spotify_episode_id": "abc"}, 5000
    ) == "https://open.spotify.com/episode/abc?t=5"
    assert (
        spotify_episode_id_from_transcript_url(
            "https://transcript-files.spotifycdn.com/0ibUtrJG4JVgwfvB2MXMSb/0T15bGPizAqgJgQA3rnsv4/transcript.srt"
        )
        == "0T15bGPizAqgJgQA3rnsv4"
    )


def test_lexical_pipeline_uses_fuzzy_on_standard_multi_fields():
    pipeline = lexical_pipeline("gsming", "podcast_search_index", 10)
    clauses = pipeline[0]["$search"]["compound"]["should"]
    fuzzy_paths = {
        clause["text"]["path"]
        for clause in clauses
        if clause["text"].get("fuzzy")
    }
    assert "episode_title.fuzzy" in fuzzy_paths
    assert "text.fuzzy" in fuzzy_paths
    assert FUZZY["maxEdits"] == 2
    assert FUZZY["prefixLength"] == 0


def test_rank_fusion_pipeline_blends_vector_and_search():
    pipeline = rank_fusion_pipeline(
        "document modeling",
        search_index="podcast_search_index",
        vector_index="podcast_vector_index",
        model="voyage-4",
        limit=10,
    )
    fusion = pipeline[0]["$rankFusion"]["input"]["pipelines"]
    vector = fusion["vectorPipeline"][0]["$vectorSearch"]
    assert vector["path"] == "text"
    assert vector["query"] == {"text": "document modeling"}
    assert vector["model"] == "voyage-4"
    assert "$search" in fusion["textPipeline"][0]


def test_levenshtein_gsming_gaming():
    assert levenshtein("gsming", "gaming") == 1


def test_rrf_prefers_docs_in_both_lists():
    lexical = [
        {"_id": "a", "episode_id": "e1", "text": "alpha", "score": 4},
        {"_id": "b", "episode_id": "e2", "text": "beta", "score": 3},
    ]
    vector = [
        {"_id": "c", "episode_id": "e3", "text": "gamma", "score": 0.9},
        {"_id": "a", "episode_id": "e1", "text": "alpha", "score": 0.8},
    ]
    ranked = reciprocal_rank_fusion(lexical, vector)
    assert ranked[0]["_id"] == "a"
    assert set(ranked[0]["match_types"]) == {"keyword", "semantic"}


def test_group_by_episode_keeps_podcast_order_and_caps_snippets():
    docs = [
        {
            "podcast_id": "p1",
            "podcast_title": "Show One",
            "podcast_author": "A",
            "episode_id": "e1",
            "episode_title": "Ep 1",
            "episode_url": "http://example.test/e1",
            "published_at": "2025-01-01",
            "chunk_index": 0,
            "score": 0.9,
            "match_types": ["keyword"],
            "snippet_html": "one",
        },
        {
            "podcast_id": "p1",
            "podcast_title": "Show One",
            "podcast_author": "A",
            "episode_id": "e1",
            "episode_title": "Ep 1",
            "episode_url": "http://example.test/e1",
            "published_at": "2025-01-01",
            "chunk_index": 1,
            "score": 0.4,
            "match_types": ["semantic"],
            "snippet_html": "two",
        },
        {
            "podcast_id": "p1",
            "podcast_title": "Show One",
            "podcast_author": "A",
            "episode_id": "e1",
            "episode_title": "Ep 1",
            "episode_url": "http://example.test/e1",
            "published_at": "2025-01-01",
            "chunk_index": 2,
            "score": 0.2,
            "match_types": ["semantic"],
            "snippet_html": "three",
        },
        {
            "podcast_id": "p2",
            "podcast_title": "Show Two",
            "podcast_author": "B",
            "episode_id": "e2",
            "episode_title": "Ep 2",
            "episode_url": "http://example.test/e2",
            "published_at": "2025-02-01",
            "chunk_index": 0,
            "score": 0.7,
            "match_types": ["keyword"],
            "snippet_html": "other",
        },
    ]
    grouped = group_by_episode(docs, snippets_per_episode=2)
    assert [show["podcast_id"] for show in grouped] == ["p1", "p2"]
    assert len(grouped[0]["episodes"][0]["snippets"]) == 2
    assert grouped[0]["episodes"][0]["match_types"] == ["keyword", "semantic"]


def test_snippets_are_uniquely_keyed():
    keys = [(s["episode_id"], s["chunk_index"]) for s in SNIPPETS]
    assert len(keys) == len(set(keys))
    assert all(s["text"].strip() for s in SNIPPETS)


def test_srt_to_text_strips_indexes_and_timestamps():
    srt = """1
00:00:11,120 --> 00:00:14,040
Hello everyone.

2
00:00:14,040 --> 00:00:17,200
Welcome to <b>MongoDB</b>.
"""
    assert srt_to_text(srt) == "Hello everyone. Welcome to MongoDB."
    cues = parse_srt_cues(srt)
    assert cues[0].start_ms == 11120
    assert cues[1].end_ms == 17200


def test_chunk_cues_keeps_start_and_end():
    cues = [
        Cue(start_ms=1000, end_ms=2000, text="Hello there."),
        Cue(start_ms=2000, end_ms=3500, text="This is later."),
        Cue(start_ms=90000, end_ms=95000, text="A much later sentence that should start a new chunk because it will not fit."),
    ]
    chunks = chunk_cues(cues, max_chars=40)
    assert chunks[0]["start_ms"] == 1000
    assert chunks[0]["end_ms"] == 3500
    assert chunks[-1]["start_ms"] == 90000


def test_chunk_transcript_respects_max_chars():
    text = "Hello world. " * 40
    chunks = chunk_transcript(text, max_chars=80)
    assert chunks
    assert all(len(chunk) <= 80 for chunk in chunks)


def test_highlight_wraps_hits():
    html = highlight_html(
        [{"texts": [{"value": "hello ", "type": "text"}, {"value": "world", "type": "hit"}]}],
        "hello world",
    )
    assert html == "hello <mark>world</mark>"
