"""Deterministic grading. No model, no API cost, no judgement.

Everything here is a string or a boolean. The judge is only reached for
semantic coverage, because every judged case is a case you have to trust.
"""
import re
from typing import Any, Dict, List

DECLINE = re.compile(
    r"do(es)? not (contain|specify|state|provide)|not (possible|able) to determine"
    r"|cannot be determined|no information|not stated|insufficient|unable to"
    r"|which (product|sourdough|loaf|oven)|as at (what|which) date|could you clarify|please specify",
    re.I,
)


def entities_from(manifest: Dict[str, Any]) -> List[str]:
    """Closed vocabulary of named things, longest first so 'Birch Lane Mill'
    is matched before 'Birch Lane'."""
    ents = []
    e = manifest["entities"]
    for group in ("products", "ingredients", "suppliers", "sites"):
        for item in e.get(group, []):
            name = str(item.get("name", ""))
            ents.append(name)
            # the short form people actually write: "Golden Field", "High Street"
            for suffix in (" flour", " bakery"):
                if name.endswith(suffix):
                    ents.append(name[: -len(suffix)])
            if item.get("code"):
                ents.append(str(item["code"]))
            ident = str(item.get("id", ""))
            # skip bare lowercase ids (alder, birch, riverside) — their full
            # names are already in the list, and matching the id alone fires
            # on ordinary prose
            if ident and not ident.islower():
                ents.append(ident)
    ents += [str(r["id"]) for r in e.get("records", [])]
    for m in e["authority"]["matrices"]:
        if m.get("level_3_holder"):
            ents.append(str(m["level_3_holder"]))
    ents += ["withdrawal", "Level 3", "Level 1"]
    return sorted({x for x in ents if len(x) > 2}, key=len, reverse=True)


def mentioned(text: str, needles: List[str]) -> List[str]:
    return [n for n in needles if re.search(rf"(?<!\w){re.escape(n)}", text, re.I)]


MEASUREMENT = re.compile(r"\b\d+(?:\.\d+)?\s*(?:°C|g\b|mm\b|%|days?\b|months?\b|minutes?\b)", re.I)


def salient_terms(expected_text: str, vocabulary: List[str]) -> List[str]:
    """What a correct answer must contain: the named things in the expected
    answer, plus any measurement it states. The manifest's `answer` field is
    prose, so it must hold the fact and nothing else — an aside like "SD-13's
    value is the plausible wrong answer" would otherwise make SD-13 a required
    term. Asides belong in wrong_answer_path_a."""
    return mentioned(expected_text, vocabulary) + MEASUREMENT.findall(expected_text)


UNITS = re.compile(r"\s*(?:°|º|degrees?|deg)\s*C(?:elsius)?\b", re.I)


def _units(text: str) -> str:
    # "230°C", "230 degrees C" and "230 °C" state the same fact; the corpus
    # writes the last
    return UNITS.sub(" °C", text or "")


def check_expected(answer: str, expected_terms: List[str]) -> Dict[str, Any]:
    hit = mentioned(_units(answer), [_units(t) for t in expected_terms])
    return {"name": "states_expected", "passed": bool(hit) if expected_terms else None,
            "detail": f"found {hit}" if hit else f"none of {expected_terms}"}


def check_not_wrong(answer: str, wrong_terms: List[str]) -> Dict[str, Any]:
    hit = mentioned(_units(answer), [_units(t) for t in wrong_terms])
    return {"name": "avoids_known_wrong", "passed": not hit if wrong_terms else None,
            "detail": f"stated {hit}" if hit else "none of the known wrong answers"}


def check_declined(answer: str, abstained: bool, decision: str) -> Dict[str, Any]:
    declined = bool(abstained) or decision in ("clarify", "abstain") or bool(DECLINE.search(answer or ""))
    return {"name": "declined", "passed": declined,
            "detail": f"abstained={abstained} decision={decision} "
                      f"decline_language={bool(DECLINE.search(answer or ''))}"}


def check_citation_support(answer: str, cited: List[int], passages: Dict[int, Any],
                           vocabulary: List[str]) -> Dict[str, Any]:
    """The fabrication detector.

    Every named thing the answer asserts must appear in at least one passage it
    cited. This is what catches "Alder Mill, which supplies the flour for the
    withdrawn product [1]" when passage [1] says nothing about a withdrawal:
    `withdrawal` is asserted and unsupported. No model required: the entity is
    either in the cited text or it is not.
    """
    if not answer:
        return {"name": "claims_supported", "passed": None, "detail": "no answer"}
    if not cited:
        return {"name": "claims_supported", "passed": False, "detail": "answer cites nothing"}
    cited_text = " ".join(str(passages.get(n, {}).get("content", "")) or
                          str(passages.get(n, {}).get("filename", "")) for n in cited)
    asserted = mentioned(answer, vocabulary)
    unsupported = [e for e in asserted if not mentioned(cited_text, [e])]
    return {"name": "claims_supported", "passed": not unsupported,
            "detail": f"unsupported in cited passages: {unsupported}" if unsupported
                      else f"all {len(asserted)} named claims appear in cited passages"}
