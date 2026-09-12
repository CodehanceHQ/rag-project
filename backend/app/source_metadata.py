import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable


HEADER_PATTERNS = {
    "record_id": re.compile(r"^(?:Policy|Amendment|Document) ID:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    "owner": re.compile(r"^Owner:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    "source_status": re.compile(r"^Status:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    "effective_date": re.compile(r"^Effective date:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
    "superseded_date": re.compile(r"^Superseded date:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE),
}


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip().rstrip("  ")
    for pattern in ("%d %B %Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def extract_source_metadata(texts: Iterable[str]) -> Dict[str, Any]:
    header = "\n".join(texts)[:8000]
    metadata: Dict[str, Any] = {"source_status": "current"}
    for field, pattern in HEADER_PATTERNS.items():
        match = pattern.search(header)
        if not match:
            continue
        value = match.group(1).strip()
        if field.endswith("_date"):
            parsed = _parse_date(value)
            if parsed:
                metadata[field] = parsed
        elif field == "source_status":
            metadata[field] = value.casefold()
        else:
            metadata[field] = value
    return metadata
