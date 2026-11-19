from uuid import uuid4

import pytest

from agent import llm
from agent.checks import REGISTRY as CHECKS
from agent.contracts import CheckSpec, CheckType
from agent.runtime import qa
from agent.runtime.context import current_check, current_trace
from agent.runtime.planner import build_plan
from agent.runtime.tools import REGISTRY as TOOLS
from agent.runtime.tools import tool
from agent.runtime.trace import Trace
from agent.tools import TOOLS as TOOL_FUNCS


def test_every_check_declares_registered_tools():
    assert CHECKS
    for cls in CHECKS.values():
        assert cls.tools, f"{cls.__name__} declares no tools"
        assert set(cls.tools) <= set(TOOLS), f"{cls.__name__} names an unregistered tool"


def test_tool_registry_matches_tool_map():
    assert set(TOOL_FUNCS) == set(TOOLS)
    assert "session_mirrors" in TOOLS and all(t.read_only for t in TOOLS.values())


def test_tool_calls_are_traced_and_attributed():
    @tool("unit_test_tool")
    def f(n: int) -> list[int]:
        """Return n items."""
        if n < 0:
            raise ValueError("negative")
        return list(range(n))

    trace = Trace()
    t1, t2 = current_trace.set(trace), current_check.set("Q1")
    try:
        f(3)
        f(2)
        with pytest.raises(ValueError):
            f(-1)
    finally:
        current_trace.reset(t1)
        current_check.reset(t2)
        TOOLS.pop("unit_test_tool")
    trace.flush_tool_stats("Q1")
    step = trace.steps[-1]
    assert step["tool"] == "unit_test_tool" and step["status"] == "failed"
    assert step["detail"]["calls"] == 3 and step["detail"]["rows"] == 5 and step["detail"]["errors"] == 1


def test_planner_lists_tools_and_assumptions():
    trace = Trace()
    spec = CheckSpec(check_id="Q1", question_ref="Q1", question_text="Calls within hours", check_type=CheckType.CALLING_HOURS, sources=["D4"], sample={}, test={})
    plan = build_plan([spec], 300, {"label": "October 2026", "start": "2026-10-01", "end": "2026-11-01"}, "random sample", 2, trace)
    assert plan[0]["tools"] == list(CHECKS[CheckType.CALLING_HOURS].tools)
    assert any("unmatched" in s["action"] for s in trace.steps)
    assert plan[0]["notes"], "a missing severity must be noted as an assumption"


def test_qa_without_model_answers_from_findings(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(qa, "_run_tool", lambda run_id, name, args: ([{"finding_id": 7, "check_id": "Q1", "status": "gap", "severity": "Critical", "reason": "x"}], [7]))
    out = qa.ask(uuid4(), "show critical gaps in Q1")
    assert out["finding_ids"] == [7] and out["used_model"] is False


def test_qa_rejects_ids_no_query_returned(monkeypatch):
    moves = iter([{"action": "tool", "tool": "list", "args": {}},
                  {"action": "answer", "answer": "bad", "finding_ids": [999]},
                  {"action": "answer", "answer": "ok", "finding_ids": [7]}])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "reason_json", lambda *a, **k: next(moves))
    monkeypatch.setattr(qa, "_run_tool", lambda run_id, name, args: ([{"finding_id": 7}], [7]))
    out = qa.ask(uuid4(), "what happened")
    assert out["answer"] == "ok" and out["finding_ids"] == [7]
    assert any(s["status"] == "failed" and "Rejected" in s["action"] for s in out["steps"])


def test_qa_refuses_to_guess_when_it_never_answers(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "reason_json", lambda *a, **k: {"action": "tool", "tool": "summary"})
    monkeypatch.setattr(qa, "_run_tool", lambda run_id, name, args: ([], []))
    out = qa.ask(uuid4(), "anything")
    assert out["finding_ids"] == [] and "could not" in out["answer"]
