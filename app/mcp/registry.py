"""
Phase 5: MCPRegistry - Service Discovery & Load Balancing

Pragmatic approach with environment variables:
- Load replica URLs from environment variables at startup
- Monitor health every 30 seconds
- Intelligent replica selection using latency-aware scoring
- Automatic failover on consecutive errors

ENVIRONMENT VARIABLES:
  EMAIL_SERVICE_REPLICAS="http://localhost:9001,http://localhost:9002"
  CUSTOMER_SERVICE_REPLICAS="http://localhost:8001"

UPGRADE PATH (GCP/Kubernetes):
  Just replace get_replicas() to use K8s DNS - no registry changes!
"""

import asyncio
import logging
from typing import Dict, List, Optional

from app.mcp.replica_stats import ReplicaStats
from app.mcp.service_metadata import ServiceMetadata
from app.mcp.health_checker import HealthChecker, check_replica_health

logger = logging.getLogger(__name__)


class MCPRegistry:
    """Central service registry for MCP microservices."""

    def __init__(self, health_check_interval: int = 30):
        """Initialize registry."""
        self.services: Dict[str, ServiceMetadata] = {}
        self._health_checker = HealthChecker(health_check_interval)

    async def register_service(
        self,
        name: str,
        replicas: List[str],
    ) -> None:
        """
        Register a service with its replicas.

        Args:
            name: Service name (e.g., "email_service")
            replicas: List of replica URLs

        Raises:
            ValueError: If service already exists or replicas empty
        """
        if name in self.services:
            raise ValueError(f"Service '{name}' already registered")

        if not replicas:
            raise ValueError(f"Service '{name}' must have at least one replica")

        service = ServiceMetadata(name=name)
        for url in replicas:
            service.replicas[url.strip()] = ReplicaStats(url=url.strip())

        self.services[name] = service
        logger.info(
            f"Registered service '{name}' with {len(replicas)} replicas",
            extra={"replicas": replicas},
        )

    def get_healthiest(self, service_name: str) -> Optional[str]:
        """Get URL of healthiest replica for a service."""
        service = self.services.get(service_name)
        if not service:
            logger.error(f"Service '{service_name}' not found")
            return None

        best = service.get_best_replica()

        if best:
            logger.debug(
                f"Selected replica: {service_name}",
                extra={"replica": best.url, "score": f"{best.calculate_score():.2f}"},
            )
            return best.url

        logger.warning(f"No healthy replicas for '{service_name}'")
        return None

    def record_error(self, service_name: str, replica_url: str) -> None:
        """Record error for a replica."""
        service = self.services.get(service_name)
        if not service:
            return

        replica = service.replicas.get(replica_url)
        if not replica:
            return

        replica.consecutive_failures += 1
        replica.error_rate = min(5.0, replica.error_rate + 0.5)

        if replica.consecutive_failures >= 3:
            replica.status = "UNHEALTHY"
            logger.warning(
                f"Replica marked UNHEALTHY (3 failures)",
                extra={"service": service_name, "replica": replica_url},
            )

    def record_success(self, service_name: str, replica_url: str) -> None:
        """Record success for a replica."""
        service = self.services.get(service_name)
        if not service:
            return

        replica = service.replicas.get(replica_url)
        if not replica:
            return

        replica.consecutive_failures = 0
        replica.error_rate = max(0.0, replica.error_rate - 0.1)

    async def start_health_checks(self) -> None:
        """Start background health monitoring."""
        await self._health_checker.start(self._run_health_checks)

    async def stop_health_checks(self) -> None:
        """Stop background health monitoring."""
        await self._health_checker.stop()

    async def _run_health_checks(self) -> None:
        """Check health of all replicas."""
        tasks = []
        for service in self.services.values():
            for url, stats in service.replicas.items():
                tasks.append(check_replica_health(url, stats))

        await asyncio.gather(*tasks, return_exceptions=True)

    def get_status(self) -> Dict:
        """Get registry status for monitoring."""
        status = {"services": {}}

        for service_name, service in self.services.items():
            replicas_status = {}

            for url, stats in service.replicas.items():
                replicas_status[url] = {
                    "status": stats.status,
                    "latency_ms": f"{stats.latency_ms:.2f}",
                    "error_rate": f"{stats.error_rate:.1f}%",
                    "score": f"{stats.calculate_score():.2f}",
                    "healthy": stats.is_healthy(),
                }

            best = service.get_best_replica()
            status["services"][service_name] = {
                "replicas": replicas_status,
                "best_replica": best.url if best else None,
                "healthy_count": len(service.get_all_healthy()),
                "total_count": len(service.replicas),
            }

        return status


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_registry: Optional[MCPRegistry] = None


def get_registry() -> MCPRegistry:
    """Get or create the global MCPRegistry instance."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry
