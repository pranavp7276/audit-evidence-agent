"""The skeptic: a second reading of a reported gap by a model that sees only what the gap cites.

For each gap it is given the rule, the reported reason and the extracts of the cited records, and asked: do these records support this
finding? It answers supports, disputes or unclear, with one sentence naming the field that worries it. It does not see the rest of the
database, cannot change a finding, a status or a severity, and a disagreement only moves the gap up the review queue. Nothing about a
borrower is sent: phone numbers are masked to their last four digits and names are dropped before the text leaves.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from agent.core import llm

VERDICTS = ("supports", "disputes", "unclear")
_DROP = ("name", "email", "address", "pan", "aadhaar", "dob")
_SYSTEM = ("You are a sceptical senior auditor reviewing one reported gap. You see only the rule, the finding as reported, and the extracts of the "
           "records it cites. Decide whether those records, applied to the rule, support the finding. Do not assume facts that are not in the extracts. "
           "If the records support it, say supports. If they contradict it or do not show it, say disputes and name the field. If you cannot tell from "
           "what you were given, say unclear. Reply with JSON only: {\"verdict\": \"supports|disputes|unclear\", \"concern\": \"one sentence\"}.")


def _safe(extract: dict | None) -> dict:
    """The extract with phone numbers masked and personal fields removed."""
    out = {}
    for k, v in (extract or {}).items():
        low = k.lower()
        if any(w in low for w in _DROP):
            continue
        out[k] = ("X" * max(len(str(v)) - 4, 0) + str(v)[-4:]) if ("contact_no" in low or "phone" in low or "mobile" in low) and v else v
    return out


def challenge_one(item: dict) -> dict:
    """item: {finding_id, rule, reason, citations: [{source_table, record_key, record_ts_utc, role, extract}]}. Returns {finding_id, verdict, concern, model}."""
    records = [{"source": c["source_table"], "key": c["record_key"], "time_utc": str(c.get("record_ts_utc") or ""), "role": c.get("role"),
                "extract": _safe(c.get("extract"))} for c in item["citations"]]
    prompt = f"Rule being tested: {item['rule']}\n\nReported finding: {item['reason']}\n\nCited records: {records}"
    out = llm.reason_json(prompt, _SYSTEM, max_tokens=900)
    verdict = str(out.get("verdict", "")).strip().lower() if isinstance(out, dict) else ""
    concern = str(out.get("concern", "")).strip()[:400] if isinstance(out, dict) else ""
    if verdict not in VERDICTS or (verdict == "disputes" and len(concern) < 10):
        verdict, concern = "unclear", concern or "The second reading did not give a usable answer."
    return {"finding_id": item["finding_id"], "verdict": verdict, "concern": concern or None, "model": llm.models()["reasoning"]}


def challenge_many(items: list[dict], workers: int = 4, budget_s: float = 240.0) -> tuple[list[dict], int]:
    """Challenge as many items as fit in the time budget. Returns (results, how many were not reached or failed)."""
    if not items or not llm.available():
        return [], len(items)
    deadline, results = time.monotonic() + budget_s, []

    def work(item: dict) -> dict | None:
        if time.monotonic() > deadline:
            return None
        try:
            return challenge_one(item)
        except (llm.LLMError, KeyError, TypeError, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in pool.map(work, items):
            if r:
                results.append(r)
    return results, len(items) - len(results)
