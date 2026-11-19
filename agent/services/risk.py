"""Risk assessment: how likely each test is to find a gap in an audit sample, and how bad a gap on it is.

Likelihood is measured, not guessed: the share of tested accounts that had at least one gap, over every completed audit. Impact comes from the severity
the request's own scale gives that kind of gap (its place on the scale: first = 5, second = 3, later = 1). Each is put in a band, and the two bands multiply
into a rating on the usual 3 x 3 matrix. Nothing here changes a finding; it tells a team where to look first.
"""
from __future__ import annotations

from agent.core.db import connect

LIKELIHOOD_BANDS = ((0.30, "High", 3), (0.10, "Medium", 2), (0.0, "Low", 1))   # share of accounts with a gap
IMPACT_BANDS = ((5, "High", 3), (3, "Medium", 2), (0, "Low", 1))               # severity weight
SEVERITY_WEIGHT = (5, 3, 1)


def band(value: float, bands: tuple) -> tuple[str, int]:
    return next((name, idx) for floor, name, idx in bands if value >= floor)


def rating(likelihood_idx: int, impact_idx: int) -> str:
    score = likelihood_idx * impact_idx
    return "High" if score >= 6 else "Medium" if score >= 3 else "Low"


def severity_weight(rank: int | None) -> int:
    """rank is the severity's 1-based place on the request's scale; unknown or none gets the lowest weight."""
    return SEVERITY_WEIGHT[min((rank or 99) - 1, len(SEVERITY_WEIGHT) - 1)] if rank else 1


def assess() -> dict:
    """The risk matrix over every completed audit: one entry per test, and the agencies the gaps concentrate in."""
    with connect() as conn:
        tests = conn.execute(
            """SELECT c.check_type, count(DISTINCT (f.run_id, f.account_id)) AS tested,
                      count(DISTINCT (f.run_id, f.account_id)) FILTER (WHERE f.status = 'gap') AS with_gap,
                      min(COALESCE((SELECT t.ord FROM jsonb_array_elements_text(ru.severity_scale) WITH ORDINALITY t(v, ord) WHERE t.v = f.severity), 99)) FILTER (WHERE f.status = 'gap') AS rank,
                      max(COALESCE((c.test_definition->>'priority_weight')::int, 1)) AS weight
               FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) JOIN audit.runs ru USING (run_id)
               WHERE ru.status = 'completed' AND ru.kind = 'audit' AND c.check_type <> 'other' GROUP BY c.check_type""").fetchall()
        agencies = conn.execute(
            """SELECT COALESCE(k.agency, 'Unknown agency') AS agency, count(*) AS gaps,
                      sum(CASE COALESCE((SELECT t.ord FROM jsonb_array_elements_text(ru.severity_scale) WITH ORDINALITY t(v, ord) WHERE t.v = f.severity), 99)
                               WHEN 1 THEN 5 WHEN 2 THEN 3 ELSE 1 END) AS points
               FROM audit.findings f JOIN audit.runs ru USING (run_id) JOIN staging.call_sessions s ON s.session_key = f.subject_ref
               LEFT JOIN staging.collectors k ON k.user_id = s.collector_user_id::text
               WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status = 'gap' GROUP BY 1 ORDER BY points DESC, 1 LIMIT 10""").fetchall()
    out = []
    for t in tests:
        likelihood = t["with_gap"] / t["tested"] if t["tested"] else 0.0
        impact = severity_weight(t["rank"])
        l_name, l_idx = band(likelihood, LIKELIHOOD_BANDS)
        i_name, i_idx = band(impact, IMPACT_BANDS)
        out.append({"check_type": t["check_type"], "tested": t["tested"], "with_gap": t["with_gap"], "likelihood": likelihood, "likelihood_band": l_name, "impact": impact,
                    "impact_band": i_name, "rating": rating(l_idx, i_idx), "priority_weight": t["weight"], "score": round(likelihood * impact * 100)})
    out.sort(key=lambda r: (-r["score"], r["check_type"]))
    return {"tests": out, "agencies": [dict(a) for a in agencies]}
