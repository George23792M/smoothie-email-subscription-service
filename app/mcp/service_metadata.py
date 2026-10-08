"""Service metadata and replica queries."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from app.mcp.replica_stats import ReplicaStats

logger = logging.getLogger(__name__)


@dataclass
class ServiceMetadata:
    """Metadata for a registered service."""

    name: str
    replicas: Dict[str, ReplicaStats] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def get_all_healthy(self) -> List[ReplicaStats]:
        """Return list of healthy replicas."""
        return [r for r in self.replicas.values() if r.is_healthy()]

    def get_best_replica(self) -> Optional[ReplicaStats]:
        """Return replica with lowest score (best performance)."""
        healthy = self.get_all_healthy()
        if not healthy:
            return None
        return min(healthy, key=lambda r: r.calculate_score())
