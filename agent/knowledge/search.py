"""Semantic search over the compliance library: every clause of every document, embedded and held in a Faiss index.

Finds the clauses that bear on a question or a finding ("what does policy say about calls after 7 pm?"). It points a reader at policy
text; it is never evidence for a verdict, which comes from the warehouse rows a check cites.

Embeddings come from a small local model (fastembed, BAAI/bge-small-en-v1.5; nothing is sent out). Embedding the whole library takes
minutes on a slow machine, so the vectors are cached on disk by clause text and `warm()` fills the cache in the background. Until the
model's vectors cover every clause, and whenever the model cannot be loaded, clauses are embedded as hashed word and word-pair counts,
which is instant; the answer says which was used."""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path

import faiss
import numpy as np

from agent.core.db import read_rows

MODEL = "BAAI/bge-small-en-v1.5"
HASHED = "hashed words"
_HASH_DIM = 1024
_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "kb_embeddings.npz"
_lock = threading.Lock()
_state: dict = {"model": None, "vectors": {}, "indexes": {}, "warming": False}


def _hashed(texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), _HASH_DIM), dtype="float32")
    for i, t in enumerate(texts):
        words = re.findall(r"[a-z0-9]+", t.lower())
        for gram in words + [a + " " + b for a, b in zip(words, words[1:])]:
            out[i, int(hashlib.md5(gram.encode()).hexdigest(), 16) % _HASH_DIM] += 1.0
    return out


def _unit(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)


def _key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _model():
    """The loaded embedding model, or None when it cannot be loaded."""
    if _state["model"] is None:
        try:
            from fastembed import TextEmbedding
            _state["model"] = TextEmbedding(MODEL)
        except Exception:
            _state["model"] = False
    return _state["model"] or None


def _embed_model(texts: list[str]) -> np.ndarray:
    return np.array(list(_model().embed(texts)), dtype="float32")


def _load_cache() -> dict[str, np.ndarray]:
    if not _state["vectors"] and _CACHE.exists():
        try:
            data = np.load(_CACHE, allow_pickle=False)
            _state["vectors"] = dict(zip(data["keys"].tolist(), data["vecs"]))
        except Exception:
            _state["vectors"] = {}
    return _state["vectors"]


def _save_cache() -> None:
    cache = _state["vectors"]
    if cache:
        _CACHE.parent.mkdir(exist_ok=True)
        np.savez(_CACHE, keys=np.array(list(cache)), vecs=np.stack(list(cache.values())))


def _clauses() -> list[dict]:
    return read_rows("""SELECT c.doc_id, c.clause_no, c.body, d.title, d.doc_type, d.issuer, d.reference_no, d.effective_date
                        FROM audit.kb_clause c JOIN audit.kb_document d ON d.doc_id = c.doc_id ORDER BY c.doc_id, c.seq""")


def warm() -> None:
    """Embed, in a background thread, the clauses the cache does not hold yet, so later searches use the model's vectors."""
    with _lock:
        if _state["warming"]:
            return
        _state["warming"] = True

    def work() -> None:
        try:
            cache = _load_cache()
            todo = sorted({r["body"] for r in _clauses() if _key(r["body"]) not in cache})
            if todo and _model():
                for i in range(0, len(todo), 32):
                    for text, vec in zip(todo[i:i + 32], _embed_model(todo[i:i + 32])):
                        cache[_key(text)] = vec
                    _save_cache()
        except Exception:
            pass
        finally:
            _state["warming"] = False
            _state["indexes"].clear()

    threading.Thread(target=work, daemon=True, name="kb-embed").start()


def _build(rows: list[dict]) -> tuple[faiss.Index, str]:
    """A Faiss index over the clauses: the model's vectors when the cache covers every clause, otherwise hashed vectors."""
    cache = _load_cache()
    if rows and all(_key(r["body"]) in cache for r in rows):
        vecs, backend = np.stack([cache[_key(r["body"])] for r in rows]), MODEL
    else:
        vecs, backend = _hashed([r["body"] for r in rows]) if rows else np.zeros((0, _HASH_DIM), dtype="float32"), HASHED
    vecs = _unit(vecs)
    index = faiss.IndexFlatIP(vecs.shape[1])  # inner product on unit vectors is cosine similarity
    if rows:
        index.add(vecs)
    return index, backend


def _index() -> tuple[faiss.Index, list[dict], str]:
    """The index and its rows, rebuilt when the library changed or the model's vectors became complete."""
    with _lock:
        rows = _clauses()
        stamp = (len(rows), hash(tuple(r["body"] for r in rows)), len(_state["vectors"]))
        if _state["indexes"].get("stamp") != stamp:
            index, backend = _build(rows)
            _state["indexes"] = {"stamp": stamp, "index": index, "rows": rows, "backend": backend}
        s = _state["indexes"]
        return s["index"], s["rows"], s["backend"]


def search(query: str, k: int = 5, doc_type: str | None = None) -> dict:
    """The k clauses closest in meaning to the query, best first, each with its document and a 0 to 1 similarity."""
    query = query.strip()
    index, rows, backend = _index()
    if not query or not rows:
        return {"query": query, "backend": backend, "indexed": len(rows), "hits": []}
    q = _embed_model([query]) if backend == MODEL else _hashed([query])
    # the same clause often appears in many documents, so search wide and show each distinct text once, with how many documents carry it
    sims, ids = index.search(_unit(q), len(rows))
    hits: dict[str, dict] = {}
    for sim, i in zip(sims[0], ids[0]):
        r = rows[int(i)]
        if doc_type and r["doc_type"] != doc_type:
            continue
        if r["body"] in hits:
            hits[r["body"]]["also_in"] += 1
        elif len(hits) < k:
            hits[r["body"]] = {"doc_id": r["doc_id"], "document": r["title"], "doc_type": r["doc_type"], "issuer": r["issuer"], "reference_no": r["reference_no"],
                               "clause_no": r["clause_no"], "text": r["body"], "similarity": round(max(float(sim), 0.0), 3), "also_in": 0}
    return {"query": query, "backend": backend, "indexed": len(rows), "warming": _state["warming"], "hits": list(hits.values())}
