from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gnn_activation_gate(
    path: Path,
    *,
    artifact_version: str,
    graph_version: str,
) -> dict[str, Any]:
    status = {"active": False, "reason": "gate_missing", "path": str(path)}
    if not path.exists():
        return status
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {**status, "reason": "gate_invalid", "error": str(exc)}
    if gate.get("gate_schema_version") != "gnn-activation-gate-v1":
        return {**status, "reason": "gate_incompatible"}
    if not gate.get("passed"):
        return {**status, "reason": "gate_failed"}
    if gate.get("artifact_version") != artifact_version:
        return {**status, "reason": "artifact_version_mismatch"}
    if gate.get("graph_version") != graph_version:
        return {**status, "reason": "graph_version_mismatch"}
    return {"active": True, "reason": None, "path": str(path)}
