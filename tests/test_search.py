"""Semantic search over the compliance library (Faiss)."""
import numpy as np

from agent.knowledge import search as s


def test_hashed_vectors_rank_the_related_text_first():
    vecs = s._unit(s._hashed(["calls only between 8 am and 7 pm", "notices dispatched within three days", "recordings kept for twelve months"]))
    q = s._unit(s._hashed(["permitted calling hours between 8 am and 7 pm"]))
    assert int(np.argmax(vecs @ q[0])) == 0


def test_search_returns_clauses_with_their_documents():
    r = s.search("calls after the permitted hours", k=3)
    assert r["indexed"] > 0 and 0 < len(r["hits"]) <= 3
    assert all({"document", "clause_no", "text", "similarity"} <= h.keys() for h in r["hits"])
    sims = [h["similarity"] for h in r["hits"]]
    assert sims == sorted(sims, reverse=True)


def test_empty_query_returns_no_hits():
    assert s.search("   ")["hits"] == []
