"""Model-as-judge, for semantic coverage only.

Used solely where a string match cannot work — ld-01's answer is "a rejected
batch, an oven reallocated, the flour change and the allergen retest it
forced", and deciding whether a paragraph covers four causes needs a reader.

A DIFFERENT FAMILY ON PURPOSE. Path A generates on gpt-4.1-mini, and judges
favour text from their own model family, so a judge from that family would be
marking its own homework. The default belongs to another.

Its verdicts are stored per case so they can be audited rather than trusted.
Hand-grade a subset and check the judge against it.
"""
import json
import re
from typing import Any, Dict

import httpx

DEFAULT_JUDGE = "google/gemini-2.5-flash"

PROMPT = """You are grading one answer against a known-correct answer.

Judge ONLY whether the candidate states the substance of the expected answer.
Ignore style, length, hedging and extra detail. Ignore citations.

If the expected answer lists several elements, the candidate must cover them
to score covered=true. Partial coverage is covered=false.

Reply with JSON only:
{"covered": true|false, "missing": ["..."], "why": "one sentence"}"""


def judge_answer(question: str, expected: str, candidate: str,
                 api_key: str, model: str = DEFAULT_JUDGE,
                 base_url: str = "https://openrouter.ai/api/v1") -> Dict[str, Any]:
    if not candidate:
        return {"covered": False, "missing": ["no answer produced"], "why": "empty", "judge": model}
    body = {
        "model": model, "temperature": 0,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(
                {"question": question, "expected_answer": expected, "candidate_answer": candidate})},
        ],
    }
    try:
        r = httpx.post(f"{base_url.rstrip('/')}/chat/completions",
                       headers={"Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json"},
                       json=body, timeout=120.0)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        v = json.loads(m.group(0)) if m else {}
        return {"covered": bool(v.get("covered")), "missing": v.get("missing", []),
                "why": str(v.get("why", ""))[:240], "judge": model}
    except Exception as exc:
        return {"covered": None, "missing": [], "why": f"judge unavailable: {type(exc).__name__}",
                "judge": model}
