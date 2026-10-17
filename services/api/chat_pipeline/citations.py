from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .contracts import RetrievedContext


CITATION_PATTERN = re.compile(r"\[S\d+(?:\s*,\s*S\d+)*\]")
REFERENCE_PATTERN = re.compile(
    r"\[((?:S\d+|CV|KB|PDF|[\w./-]+\.(?:pdf|md|txt))"
    r"(?:\s*,\s*(?:S\d+|CV|KB|PDF|[\w./-]+\.(?:pdf|md|txt)))*)\](?!\()",
    re.IGNORECASE,
)


def extract_citation_ids(answer: str) -> List[str]:
    return list(dict.fromkeys(
        citation_id.strip().upper() if re.fullmatch(r"(?:S\d+|CV|KB|PDF)", citation_id.strip(), re.IGNORECASE)
        else citation_id.strip()
        for group in REFERENCE_PATTERN.findall(answer or "")
        for citation_id in group.split(",")
    ))


UNCERTAINTY_MARKERS = (
    "insufficient evidence",
    "not enough evidence",
    "couldn't find enough",
    "could not find enough",
    "cannot verify",
    "can't verify",
    "could not verify",
    "no information available",
    "information is not available",
    "does not mention",
    "doesn't mention",
    "don't have",
    "do not have",
)


def _canonical_source(source: str) -> str:
    normalized = source.lower().replace("\\", "/")
    return re.sub(r"^kb/", "", normalized)


def register_citation_source(
    context: RetrievedContext,
    source: str,
    channels: Iterable[str],
) -> str:
    citation_sources: List[Dict[str, Any]] = context.metadata.setdefault("citation_sources", [])
    canonical_source = _canonical_source(source)
    for item in citation_sources:
        if item["canonical_source"] == canonical_source:
            item["channels"] = sorted(set(item["channels"]).union(channels))
            return item["id"]
    citation_id = f"S{len(citation_sources) + 1}"
    citation_sources.append(
        {
            "id": citation_id,
            "source": source,
            "canonical_source": canonical_source,
            "channels": sorted(set(channels)),
        }
    )
    return citation_id


@dataclass(frozen=True)
class CitationValidation:
    valid: bool
    required: bool
    cited_ids: List[str]
    valid_ids: List[str]
    invalid_ids: List[str]
    precision: float
    uncertainty: bool
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "required": self.required,
            "cited_ids": self.cited_ids,
            "valid_ids": self.valid_ids,
            "invalid_ids": self.invalid_ids,
            "precision": self.precision,
            "uncertainty": self.uncertainty,
            "reason": self.reason,
        }


def validate_citations(answer: str, context: RetrievedContext) -> CitationValidation:
    available_ids = {item["id"] for item in context.metadata.get("citation_sources", [])}
    required = bool(context.metadata.get("grounding_required"))
    cited_ids = extract_citation_ids(answer)
    valid_ids = [citation_id for citation_id in cited_ids if citation_id in available_ids]
    invalid_ids = [citation_id for citation_id in cited_ids if citation_id not in available_ids]
    precision = len(valid_ids) / len(cited_ids) if cited_ids else (1.0 if not required else 0.0)
    uncertainty = any(marker in (answer or "").lower() for marker in UNCERTAINTY_MARKERS)

    if invalid_ids:
        valid, reason = False, "unknown_citation_ids"
    elif required and not valid_ids and not uncertainty:
        valid, reason = False, "missing_required_citation"
    elif required and not valid_ids and uncertainty:
        valid, reason = True, "explicit_uncertainty"
    else:
        valid, reason = True, "valid"
    return CitationValidation(
        valid=valid,
        required=required,
        cited_ids=cited_ids,
        valid_ids=valid_ids,
        invalid_ids=invalid_ids,
        precision=precision,
        uncertainty=uncertainty,
        reason=reason,
    )


def grounding_fallback() -> str:
    return (
        "I couldn't find enough verified evidence to answer that reliably, so I won't make an "
        "unsupported claim. Please ask about a specific project, skill, role, or experience."
    )


def repair_missing_citation(answer: str, context: RetrievedContext) -> str:
    if CITATION_PATTERN.search(answer or ""):
        return answer
    if any(marker in (answer or "").lower() for marker in UNCERTAINTY_MARKERS):
        return answer
    sources = context.metadata.get("citation_sources", [])
    persona_source = next(
        (item for item in sources if "persona" in item.get("channels", [])),
        None,
    )
    selected = persona_source
    if not selected or not (answer or "").strip():
        return answer
    return answer.rstrip() + f" [{selected['id']}]"


def format_source_legend(context: RetrievedContext, cited_ids: Iterable[str]) -> str:
    cited = set(cited_ids)
    sources = [
        item
        for item in context.metadata.get("citation_sources", [])
        if item["id"] in cited
    ]
    if not sources:
        return ""
    lines = [f"- [{item['id']}] {item['source']}" for item in sources]
    return "\n\nSources:\n" + "\n".join(lines)
