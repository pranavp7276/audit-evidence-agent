"""Evidence tag coverage: does the system capture what each check needs to create its evidence?

config/evidence_tags.yaml says what every activity should carry; config/source_map.yaml says where this database holds each of those tags. This
reads both, verifies that every column the map names exists, that every check it names is implemented, and that nothing in the spec is unmapped,
then says per catalog check whether it can run and which tags are missing. A tag that is "not captured" is a gap in the source system; one that
is "not needed" is deliberately not stored.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from agent.checks import REGISTRY
from agent.core.db import read_rows

CONFIG = Path(__file__).resolve().parents[2] / "config"
STATUSES = ("present", "derived", "available", "not_captured", "not_needed", "not_in_scope")
CAPTURED = ("present", "derived", "available")
LABEL = {"present": "Stored", "derived": "Computed by a check", "available": "Held, no check yet", "not_captured": "Not captured", "not_needed": "Not needed",
         "not_in_scope": "Not in this dataset"}


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def _name(item: dict) -> str:
    return item.get("field") or item.get("flag") or item.get("tag") or item.get("log")


def _items(spec: dict) -> list[dict]:
    """Every field, flag, transcript tag and master field in the tag spec, with where it sits and what feeds on it."""
    out = [{"section": "common_envelope", "kind": "field", "name": _name(x), "req": x.get("req"), "cn": x.get("cn"), "feeds": []} for x in spec["common_envelope"]]
    for entity, body in spec["entities"].items():
        for kind, key in (("field", "fields"), ("flag", "flags"), ("tag", "transcript_tags")):
            out += [{"section": entity, "kind": kind, "name": _name(x), "req": x.get("req"), "cn": x.get("cn"), "feeds": x.get("feeds", [])} for x in body.get(key, [])]
    for master, body in spec["masters"].items():
        out += [{"section": master, "kind": "field", "name": _name(x), "req": x.get("req"), "cn": x.get("cn"), "feeds": body.get("feeds", [])} for x in body["fields"]]
    out += [{"section": "system_logs", "kind": "log", "name": _name(x), "req": None, "cn": x.get("cn"), "feeds": x.get("feeds", [])} for x in spec["system_logs"]]
    return out


def _mapping(smap: dict, item: dict) -> dict | None:
    sec = smap["common_envelope"] if item["section"] == "common_envelope" else smap["system_logs"] if item["section"] == "system_logs" else None
    if sec is None and item["section"] in smap["entities"]:
        body = smap["entities"][item["section"]]
        sec = body["fields" if item["kind"] == "field" else "flags" if item["kind"] == "flag" else "transcript_tags"]
        return sec.get(item["name"]) or sec.get("_all")
    if sec is None:
        sec = smap["masters"].get(item["section"], {})
    return sec.get(item["name"])


def _columns(refs: set[str]) -> set[str]:
    """Which of 'schema.table.column' exist (tables and views alike)."""
    pairs = sorted({tuple(r.rsplit(".", 1)[0].split(".")) for r in refs})
    if not pairs:
        return set()
    rows = read_rows("SELECT table_schema || '.' || table_name || '.' || column_name AS ref FROM information_schema.columns "
                     "WHERE table_schema = ANY(%s) AND table_name = ANY(%s)", ([p[0] for p in pairs], [p[1] for p in pairs]))
    return {r["ref"] for r in rows}


def coverage() -> dict:
    spec, smap, catalog = _load("evidence_tags.yaml"), _load("source_map.yaml"), _load("check_catalog.yaml")
    items = _items(spec)
    implemented = {t.value for t in REGISTRY}
    refs = set()
    for it in items:
        m = _mapping(smap, it) or {}
        refs |= set(m.get("at", [])) | set(m.get("from", []))
    existing = _columns(refs)
    problems: list[str] = []
    for it in items:
        m = _mapping(smap, it)
        if m is None:
            problems.append(f"{it['section']} / {it['name']}: not in config/source_map.yaml")
            it.update(status="unmapped", where=[], reason="", note="")
            continue
        status = m["status"]
        where = m.get("at", []) or m.get("from", [])
        for col in where:
            if col not in existing:
                problems.append(f"{it['section']} / {it['name']}: column {col} does not exist")
        if status == "derived" and m.get("by") not in implemented:
            problems.append(f"{it['section']} / {it['name']}: check {m.get('by')} is not implemented")
        it.update(status=status, where=where, by=m.get("by"), reason=m.get("reason", ""), note=m.get("note", ""), feeds=m.get("for", it["feeds"]))
    counts = Counter(i["status"] for i in items if i["status"] != "unmapped")
    by_id = {c["id"]: c for c in catalog["checks"]}
    checks = []
    for cid, c in by_id.items():
        impl = smap["checks"].get(cid)
        needs = [i for i in items if cid in i["feeds"]]
        missing = [i for i in needs if i["status"] == "not_captured"]
        state = "not built" if not impl else "runs" if not missing else "partly"
        if not impl and not missing and needs:
            state = "data ready, not built"
        if not impl and not needs and c.get("engine") in ("deterministic", "hybrid"):
            state = "not built"
        checks.append({"id": cid, "name": c["name"], "engine": c["engine"], "implemented": impl, "state": state, "needs": len(needs),
                       "missing": [{"name": i["name"], "reason": i["reason"]} for i in missing]})
    return {"items": items, "counts": {s: counts.get(s, 0) for s in STATUSES}, "checks": checks, "problems": problems,
            "build": {"runs": sum(c["state"] == "runs" for c in checks), "total": len(checks)}}


def render_markdown(cov: dict) -> str:
    c = cov["counts"]
    out = ["# Evidence tag coverage", "",
           "Generated by `python -m agent tags` from `config/evidence_tags.yaml`, `config/source_map.yaml` and the database. Do not edit by hand.", "",
           f"{sum(c.values())} tags in the spec: " + ", ".join(f"{LABEL[s].lower()} {c[s]}" for s in STATUSES) + ".", "",
           f"{cov['build']['runs']} of {cov['build']['total']} catalog checks run with every tag they need.", ""]
    if cov["problems"]:
        out += ["## Problems with the map", ""] + [f"- {p}" for p in cov["problems"]] + [""]
    out += ["## Catalog checks", "", "| Check | Name | State | Tags missing |", "|---|---|---|---|"]
    for k in cov["checks"]:
        out.append(f"| {k['id']} | {k['name']} | {k['state']} | " + ("; ".join(f"{m['name']}" for m in k["missing"]) or "none") + " |")
    out += ["", "## Not captured: gaps in the source system", "", "| Tag | Section | Why |", "|---|---|---|"]
    out += [f"| {i['name']} | {i['section']} | {i['reason']} |" for i in cov["items"] if i["status"] == "not_captured"]
    out += ["", "## Not stored on purpose", "", "| Tag | Section | Why |", "|---|---|---|"]
    out += [f"| {i['name']} | {i['section']} | {i['reason']} |" for i in cov["items"] if i["status"] == "not_needed"]
    out += ["", "## Where each captured tag lives", "", "| Tag | Section | State | Where |", "|---|---|---|---|"]
    out += [f"| {i['name']} | {i['section']} | {LABEL[i['status']]} | {', '.join(i['where']) or (i.get('by') or '')} |" for i in cov["items"] if i["status"] in CAPTURED]
    return "\n".join(out) + "\n"
