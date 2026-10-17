from __future__ import annotations

import hashlib
import threading
from typing import Any


class GNNCanaryController:
    def __init__(
        self,
        percentage: float,
        *,
        salt: str,
        minimum_samples: int = 20,
        maximum_fallback_rate: float = 0.10,
    ) -> None:
        if not 0.0 <= percentage <= 100.0:
            raise ValueError("GNN canary percentage must be between 0 and 100")
        self.percentage = percentage
        self.salt = salt
        self.minimum_samples = minimum_samples
        self.maximum_fallback_rate = maximum_fallback_rate
        self._lock = threading.Lock()
        self._decisions = 0
        self._selected = 0
        self._completed = 0
        self._fallbacks = 0
        self._active_rankings = 0
        self._latency_total_ms = 0.0
        self._tripped = False
        self._trip_reason: str | None = None

    def decide(self, session_id: str) -> dict[str, Any]:
        digest = hashlib.sha256(f"{self.salt}:{session_id}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") / (2**64) * 100.0
        with self._lock:
            selected = not self._tripped and bucket < self.percentage
            self._decisions += 1
            self._selected += int(selected)
            return {
                "eligible": True,
                "selected": selected,
                "bucket": round(bucket, 6),
                "percentage": self.percentage,
                "circuit_open": self._tripped,
            }

    def record(
        self,
        decision: dict[str, Any],
        mode: str,
        latency_ms: float,
        fallback_reason: str | None = None,
    ) -> None:
        if not decision.get("selected"):
            return
        if mode == "fallback" and fallback_reason == "query_entities_unavailable":
            return
        with self._lock:
            self._completed += 1
            self._fallbacks += int(mode == "fallback")
            self._active_rankings += int(mode == "active")
            self._latency_total_ms += max(latency_ms, 0.0)
            fallback_rate = self._fallbacks / self._completed
            if self._completed >= self.minimum_samples and fallback_rate > self.maximum_fallback_rate:
                self._tripped = True
                self._trip_reason = "fallback_rate_exceeded"

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "percentage": self.percentage,
                "decisions": self._decisions,
                "selected": self._selected,
                "completed": self._completed,
                "active_rankings": self._active_rankings,
                "fallbacks": self._fallbacks,
                "fallback_rate": self._fallbacks / self._completed if self._completed else 0.0,
                "mean_reranking_latency_ms": (
                    self._latency_total_ms / self._completed if self._completed else 0.0
                ),
                "minimum_samples": self.minimum_samples,
                "maximum_fallback_rate": self.maximum_fallback_rate,
                "circuit_open": self._tripped,
                "trip_reason": self._trip_reason,
            }
