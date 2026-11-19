import httpx
import pytest

from agent import llm
from agent.contracts import CheckType, Request
from agent.parser import request_parser as rp

KEY = "sk_test_do_not_leak_0123456789"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("LLM_DISABLE", "0")
    monkeypatch.setenv("SARVAM_API_KEY", KEY)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert not llm.available()
    with pytest.raises(llm.LLMError):
        llm.reason("hi")


def test_reason_sends_key_in_header_and_returns_content_only(on):
    seen = {}

    def handler(req: httpx.Request):
        seen["key"], seen["body"] = req.headers["api-subscription-key"], req.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": " answer ", "reasoning_content": "private thoughts"}}]})

    assert llm.reason("q", client=client(handler)) == "answer"
    assert seen["key"] == KEY and KEY not in seen["body"]  # the key travels only in the header, never in the payload


def test_reason_json_tolerates_fences_and_chatter(on):
    def handler(req):
        return httpx.Response(200, json={"choices": [{"message": {"content": 'Sure:\n```json\n{"controls": ["calling_hours"]}\n```'}}]})
    assert llm.reason_json("q", client=client(handler)) == {"controls": ["calling_hours"]}


def test_decide_returns_answers(on):
    def handler(req):
        return httpx.Response(200, json={"answers": {"c": {"type": "choice", "choice": "calling_hours", "confidence": 0.9}}})
    assert llm.decide("s", {"c": {"type": "choice", "instructions": "i", "criteria": {"a": "b"}}}, client=client(handler))["c"]["choice"] == "calling_hours"


def test_errors_never_contain_the_key(on):
    for status in (401, 500):
        with pytest.raises(llm.LLMError) as e:
            llm._post("/v2/x", {}, client(lambda req, s=status: httpx.Response(s, text=f"echo {KEY}")))
        assert KEY not in str(e.value)


def test_account_list_is_withheld_before_text_leaves():
    text = "Q1. Consent?\nSampled accounts:\nCNF111111111, CNF222222222"
    out = llm.strip_sample(text)
    assert "CNF111111111" not in out and "Q1. Consent?" in out


def test_bundled_question_is_split_by_the_reasoning_model(on, monkeypatch):
    monkeypatch.setattr(llm, "decide", lambda state, q, client=None: {"check_type": {"choice": "calling_hours", "confidence": 0.9}, "bundles": {"noul": 0.9}})
    monkeypatch.setattr(llm, "reason_json", lambda *a, **k: {"controls": ["calling_hours", "calling_frequency", "made_up"]})
    checks, _, info = rp.parse_checks_with_info(Request(request_id="T", source="text", text="Q1. Calls were within policy and limits."))
    assert [c.check_type for c in checks] == [CheckType.CALLING_HOURS, CheckType.CALLING_FREQUENCY]  # an unknown id from the model is ignored
    assert [c.check_id for c in checks] == ["Q1a", "Q1b"] and info["reader"] == "models"


def test_low_confidence_is_flagged_and_service_failure_falls_back(on, monkeypatch):
    monkeypatch.setattr(llm, "decide", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("down")))
    checks, _, info = rp.parse_checks_with_info(Request(request_id="T", source="text", text="Q1. Show consent before every WhatsApp message."))
    assert info["reader"] == "keyword" and "keyword reader was used" in info["note"]  # the screen is told the models were not used
    assert [c.check_type for c in checks] == [CheckType.CONSENT_BEFORE_CONTACT]
