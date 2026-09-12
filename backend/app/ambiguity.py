import json
from typing import Any, Dict, List, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings


class ClarificationOption(BaseModel):
    label: str = Field(min_length=2, max_length=80)
    refined_query: str = Field(min_length=2, max_length=300)
    evidence_ids: List[str] = Field(min_length=1, max_length=6)


class AmbiguityDecision(BaseModel):
    decision: Literal["answer", "clarify"]
    reason: str = Field(min_length=2, max_length=300)
    clarification_question: str = Field(max_length=300)
    options: List[ClarificationOption] = Field(max_length=4)


AMBIGUITY_SCHEMA = {
    "name": "retrieval_ambiguity_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["answer", "clarify"]},
            "reason": {"type": "string"},
            "clarification_question": {"type": "string"},
            "options": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "refined_query": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["label", "refined_query", "evidence_ids"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["decision", "reason", "clarification_question", "options"],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """You are the ambiguity gate in a retrieval pipeline.
Decide whether the user's query has one coherent interpretation in the supplied evidence or several materially different interpretations that require the user to choose.

Use `clarify` only when at least two well-supported interpretations would lead to different answers. Complementary passages about the same requested subject are not ambiguity. Different document versions are handled by metadata and are not ambiguity. Do not answer the query and do not introduce facts outside the evidence.

For `clarify`, write one concise question and two to four distinct options. Each option must contain a refined standalone query and only evidence IDs supplied below. For `answer`, return an empty clarification question and no options."""


def should_check_ambiguity(candidates: List[Dict[str, Any]]) -> bool:
    if len(candidates) < 2 or not settings.openrouter_api_key:
        return False
    return candidates[0]["reranker_score"] - candidates[1]["reranker_score"] <= settings.ambiguity_score_margin


def detect_ambiguity(query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not settings.openrouter_api_key:
        return {"status": "not_configured", "decision": "answer", "reason": None, "question": None, "options": []}
    if not should_check_ambiguity(candidates):
        return {"status": "skipped", "decision": "answer", "reason": None, "question": None, "options": []}

    selected = candidates[: settings.ambiguity_max_candidates]
    evidence = [
        {
            "id": str(item["_id"]),
            "filename": item["filename"],
            "section": item.get("section"),
            "relevance_score": round(item["reranker_score"], 6),
            "content": item["content"][:1500],
        }
        for item in selected
    ]
    payload = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"query": query, "evidence": evidence})},
        ],
        "response_format": {"type": "json_schema", "json_schema": AMBIGUITY_SCHEMA},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    try:
        response = httpx.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.openrouter_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        decision = AmbiguityDecision.model_validate_json(content)
        allowed_ids = {item["id"] for item in evidence}
        options = [
            {
                "label": option.label,
                "refined_query": option.refined_query,
                "evidence_ids": [value for value in option.evidence_ids if value in allowed_ids],
            }
            for option in decision.options
        ]
        options = [option for option in options if option["evidence_ids"]]
        if decision.decision == "clarify" and len(options) < 2:
            raise ValueError("The ambiguity response did not contain two evidence-backed options.")
        return {
            "status": "checked",
            "decision": decision.decision,
            "reason": decision.reason,
            "question": decision.clarification_question or None,
            "options": options if decision.decision == "clarify" else [],
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
        return {
            "status": "error",
            "decision": "answer",
            "reason": f"Ambiguity check unavailable: {type(exc).__name__}",
            "question": None,
            "options": [],
        }
