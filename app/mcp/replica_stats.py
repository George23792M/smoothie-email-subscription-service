"""Replica statistics and scoring."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReplicaStats:
    """Statistics for a single service replica."""

    url: str
    status: str = "UNKNOWN"  # HEALTHY, UNHEALTHY, UNKNOWN
    latency_ms: float = 0.0
    error_rate: float = 0.0  # 0.0-5.0
    consecutive_failures: int = 0
    last_health_check: Optional[datetime] = None

    def is_healthy(self) -> bool:
        """Check if replica meets health criteria."""
        return (
            self.status == "HEALTHY"
            and self.consecutive_failures == 0
            and self.latency_ms < 5000
        )

    def calculate_score(self) -> float:
        """
        Score for replica quality (lower = better).
        Score = (70% latency) + (30% error_rate)
        """
        if not self.is_healthy():
            return 999.0

        latency_score = min(100.0, (self.latency_ms / 1000.0) * 100.0)
        error_score = self.error_rate * 20.0

        return 0.70 * latency_score + 0.30 * error_score
