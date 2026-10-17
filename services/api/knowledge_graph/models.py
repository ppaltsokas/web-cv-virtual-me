from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class NodeLabel(str, Enum):
    PERSON = "Person"
    PROJECT = "Project"
    SKILL = "Skill"
    TECHNOLOGY = "Technology"
    EMPLOYER = "Employer"
    ROLE = "Role"
    EDUCATION = "Education"
    CERTIFICATION = "Certification"
    DOCUMENT = "Document"
    CHUNK = "Chunk"
    CLAIM = "Claim"


class RelationshipType(str, Enum):
    BUILT = "BUILT"
    USES = "USES"
    DEMONSTRATES = "DEMONSTRATES"
    WORKED_AT = "WORKED_AT"
    HELD_ROLE = "HELD_ROLE"
    STUDIED_AT = "STUDIED_AT"
    EARNED = "EARNED"
    EVIDENCED_BY = "EVIDENCED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    RELATED_TO = "RELATED_TO"


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE).strip()


def stable_id(label: NodeLabel | str, natural_key: str) -> str:
    label_value = label.value if isinstance(label, NodeLabel) else str(label)
    # Identity preserves punctuation (C++, C#) and non-Latin owner names.
    key = " ".join(unicodedata.normalize("NFKC", natural_key).casefold().split())
    digest = hashlib.sha256(f"{label_value}:{key}".encode("utf-8")).hexdigest()[:20]
    return f"{label_value.lower()}:{digest}"


def content_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


class GraphNode(BaseModel):
    id: str
    label: NodeLabel
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    source_path: str
    source_hash: str
    extraction_method: str = "deterministic"
    confidence: float = 1.0

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    def neo4j_properties(self, ingestion_version: str) -> Dict[str, Any]:
        return {
            **self.properties,
            "id": self.id,
            "name": self.name,
            "normalized_name": normalize_name(self.name),
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "ingestion_version": ingestion_version,
            "managed_by": "virtual-persona-ingester",
        }


class GraphRelationship(BaseModel):
    source_id: str
    target_id: str
    type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    source_path: str
    source_hash: str
    extraction_method: str = "deterministic"
    confidence: float = 1.0

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @property
    def id(self) -> str:
        return content_hash(f"{self.source_id}:{self.type.value}:{self.target_id}")[:24]

    def neo4j_properties(self, ingestion_version: str) -> Dict[str, Any]:
        return {
            **self.properties,
            "id": self.id,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "ingestion_version": ingestion_version,
            "managed_by": "virtual-persona-ingester",
        }


class GraphSnapshot(BaseModel):
    ingestion_version: str
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]
    source_files: int

    def canonical_json(self) -> str:
        payload = {
            "nodes": sorted((node.model_dump(mode="json") for node in self.nodes), key=lambda item: item["id"]),
            "relationships": sorted(
                (relationship.model_dump(mode="json") for relationship in self.relationships),
                key=lambda item: (item["source_id"], item["type"], item["target_id"]),
            ),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)
