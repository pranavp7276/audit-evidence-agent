"""The verifier: after the findings are written, read every cited record back from its source table.

"Every statement traceable to a record" is easy to claim and easy to break (a key that changed, a record that was reloaded). This step does not trust
the citations: it looks each one up again through the warehouse SQL tool and reports how many resolve. A citation that does not resolve is reported
as such, never hidden.
"""
from __future__ import annotations

import time

from agent.core.contracts import Finding
from agent.core.trace import Trace
from agent.tools.record_keys import verify_records


def verify_citations(trace: Trace, results: dict[str, list[Finding]]) -> dict:
    """Returns {checked, verified, missing}: distinct cited records, how many were found in the warehouse, and those that were not."""
    t0 = time.perf_counter()
    refs = {(c.source_table, c.record_key) for fs in results.values() for f in fs for c in f.citations}
    verified, missing = verify_records(refs)
    trace.step("verify", "verifier",
               f"Read back {len(refs):,} cited record(s) from their source tables with the warehouse SQL tool: {verified:,} found"
               + (f", {len(missing)} not found" if missing else ", none missing") + ".",
               tool="warehouse_sql", status="failed" if missing else "ok", detail={"checked": len(refs), "verified": verified, "missing": missing[:20]},
               ms=(time.perf_counter() - t0) * 1000)
    return {"checked": len(refs), "verified": verified, "missing": missing[:50]}
