"""Deterministic grading. No model, no API cost, no judgement.

Everything here is a string or a boolean. The judge is only reached for
semantic coverage, because every judged case is a case you have to trust.
"""
import re
from typing import Any, Dict, List

DECLINE = re.compile(
    r"do(es)? not (contain|specify|state|provide)|not (possible|able) to determine"
    r"|cannot be determined|no information|not stated|insufficient|unable to"
    r"|which assembly|as at (what|which) date|could you clarify|please specify",
    re.I,
)


def entities_from(manifest: Dict[str, Any]) -> List[str]:
    """Closed vocabulary of named things, longest first so 'Beta Valve Co.'
    is matched before 'Beta'."""
    ents = []
    e = manifest["entities"]
    for group in ("parts", "suppliers", "plants"):
        for item in e.get(group, []):
            ents.append(str(item.get("name", "")))
            ident = str(item.get("id", ""))
            # skip bare lowercase ids (alpha, beta, bamberg) — their full names
            # are already in the list, and matching the id alone fires on
            # ordinary prose and on the other supplier's name
            if ident and not ident.islower():
                ents.append(ident)
    ents += [str(r["id"]) for r in e.get("records", [])]
    for m in e["authority"]["matrices"]:
        if m.get("level_3_holder"):
            ents.append(str(m["level_3_holder"]))
    ents += ["recall", "Bamberg", "Kassel", "Ingolstadt", "Level 3", "Level 1"]
    return sorted({x for x in ents if len(x) > 2}, key=len, reverse=True)


def mentioned(text: str, needles: List[str]) -> List[str]:
    return [n for n in needles if re.search(rf"(?<!\w){re.escape(n)}", text, re.I)]


MEASUREMENT = re.compile(r"\b\d+(?:\.\d+)?\s*(?:degC|Nm|mm|%|days?|months?|minutes?)\b", re.I)


def salient_terms(expected_text: str, vocabulary: List[str]) -> List[str]:
    """What a correct answer must contain: the named things in the expected
    answer, plus any measurement it states. The manifest's `answer` field is
    prose, so it must hold the fact and nothing else — an aside like "BV-13's
    value is the plausible wrong answer" would otherwise make BV-13 a required
    term. Asides belong in wrong_answer_path_a."""
    return mentioned(expected_text, vocabulary) + MEASUREMENT.findall(expected_text)


UNITS = re.compile(r"\s*(?:°|º|degrees?)\s*C(?:elsius)?\b", re.I)


def check_expected(answer: str, expected_terms: List[str]) -> Dict[str, Any]:
    # "180°C" and "180 degC" state the same fact; the corpus writes the latter
    hit = mentioned(UNITS.sub(" degC", answer or ""), expected_terms)
    return {"name": "states_expected", "passed": bool(hit) if expected_terms else None,
            "detail": f"found {hit}" if hit else f"none of {expected_terms}"}


def check_not_wrong(answer: str, wrong_terms: List[str]) -> Dict[str, Any]:
    hit = mentioned(answer, wrong_terms)
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
    cited. This is what catches "Alpha Dichtungen GmbH, which supplies the part
    that failed in the recall [1]" — passage [1] contains no recall reference,
    so `recall` is asserted and unsupported. No model required: the entity is
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
