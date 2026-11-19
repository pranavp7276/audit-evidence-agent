"""Model access (Sarvam API): a reasoning model, a conversational model and a decision model.

  reason()  DeepSeek (LLM_REASONING_MODEL): interprets text and returns structured output (reading a request, extracting limits)
  chat()    Sarvam conversational model (LLM_CHAT_MODEL): the help assistant
  decide()  sarvam-prism (DECISION_MODEL): picks one option per question with a confidence (which check a question maps to)

Models only interpret and assist. Pass or fail is decided by deterministic code in agent/checks (docs/decisions.md D-007).
Nothing about a borrower is sent: callers send the request's wording, or a policy clause, never account or contact data.
The API key comes from SARVAM_API_KEY in the environment (.env, git-ignored). It is never logged or returned.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

TIMEOUT = 60.0


class LLMError(RuntimeError):
    """The model service could not be used. The message never contains the API key."""


def available() -> bool:
    return bool(os.environ.get("SARVAM_API_KEY")) and os.environ.get("LLM_DISABLE") != "1"


def models() -> dict[str, str]:
    return {"reasoning": os.environ.get("LLM_REASONING_MODEL", "deepseekv4.1-flash-1017"),
            "chat": os.environ.get("LLM_CHAT_MODEL", "sarvam-105b-conversations"),
            "decision": os.environ.get("DECISION_MODEL", "sarvam-prism")}


def _post(path: str, body: dict, client: httpx.Client | None = None) -> dict:
    key = os.environ.get("SARVAM_API_KEY")
    if not key or os.environ.get("LLM_DISABLE") == "1":
        raise LLMError("No model key is configured (SARVAM_API_KEY).")
    url = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/") + path
    headers = {"api-subscription-key": key, "Content-Type": "application/json"}
    last = "unknown error"
    for attempt in (1, 2, 3):
        try:
            c = client or httpx.Client(timeout=TIMEOUT)
            try:
                r = c.post(url, headers=headers, json=body)
            finally:
                if client is None:
                    c.close()
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code < 500 and r.status_code != 429:
                raise LLMError(f"The model service refused the request ({last}).")
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        time.sleep(0.6 * attempt)
    raise LLMError(f"The model service did not respond ({last}).")


def _content(resp: dict) -> str:
    try:
        return (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise LLMError("The model returned no answer.")


def reason(prompt: str, system: str | None = None, max_tokens: int = 1500, effort: str = "low", client: httpx.Client | None = None) -> str:
    """Ask the reasoning model; returns its answer text (its reasoning trace is discarded)."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    resp = _post("/v2/chat/completions", {"model": models()["reasoning"], "messages": msgs, "temperature": 0.2, "top_p": 0.95,
                                          "max_tokens": max_tokens, "reasoning_effort": effort}, client)
    return _content(resp)


def reason_json(prompt: str, system: str | None = None, **kw: Any) -> Any:
    """Like reason(), but parses the answer as JSON (tolerating code fences and surrounding text). Retries once: the model's
    reasoning shares the token budget, so a long trace can cut the answer off."""
    kw["max_tokens"] = max(kw.get("max_tokens", 0), 1500)
    for attempt in (1, 2):
        text = re.sub(r"^```(?:json)?|```$", "", reason(prompt, system, **kw).strip(), flags=re.MULTILINE).strip()
        for start, end in (("{", "}"), ("[", "]")):
            i, j = text.find(start), text.rfind(end)
            if i != -1 and j > i:
                try:
                    return json.loads(text[i: j + 1])
                except json.JSONDecodeError:
                    continue
        kw["max_tokens"] = 3000
    raise LLMError("The model's answer was not valid JSON.")


def chat(messages: list[dict], max_tokens: int = 600, client: httpx.Client | None = None) -> str:
    """Ask the conversational model; messages are [{role, content}, ...]."""
    resp = _post("/v2/chat/completions", {"model": models()["chat"], "messages": messages, "temperature": 0.3, "top_p": 0.95,
                                          "max_tokens": max_tokens}, client)
    return _content(resp)


def decide(state: str, questions: dict[str, dict], client: httpx.Client | None = None) -> dict[str, dict]:
    """Ask the decision model several questions about one piece of text. `questions` maps a name to
    {"type": "choice", "instructions": ..., "criteria": {option: description}} or {"type": "noul", "instructions": ...}.
    A choice answer is {"choice", "confidence", "probabilities"}; a noul answer is {"noul": score between 0 and 1}."""
    resp = _post("/v2/systemone", {"model": models()["decision"], "state": state, "questions": questions}, client)
    answers = resp.get("answers")
    if not isinstance(answers, dict):
        raise LLMError("The decision model returned no answers.")
    return answers


_SAMPLE_BLOCK = re.compile(r"(sampled accounts[^\n]*:).*\Z", re.IGNORECASE | re.DOTALL)


def strip_sample(text: str) -> str:
    """The request's wording without its account list: references to loans never leave the platform."""
    return _SAMPLE_BLOCK.sub(r"\1 [list withheld]", text)
