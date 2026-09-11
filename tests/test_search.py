from search_app.chunking import chunk_transcript
from search_app.srt import srt_to_text
from search_app.search import (
    FUZZY,
    group_by_episode,
    highlight_html,
    lexical_pipeline,
    levenshtein,
    reciprocal_rank_fusion,
)
from search_app.transcripts import SNIPPETS


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
