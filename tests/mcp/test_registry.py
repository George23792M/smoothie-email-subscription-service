"""
Tests for MCPRegistry - Service discovery and load balancing.

Coverage:
- Service registration
- Health check scoring
- Best replica selection
- Error tracking
- Singleton pattern
"""

import pytest
import asyncio

from app.mcp.registry import MCPRegistry, get_registry
from app.mcp.replica_stats import ReplicaStats
from app.mcp.service_metadata import ServiceMetadata
from app.mcp.health_checker import check_replica_health

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def registry():
    """Fresh registry instance for each test."""
    return MCPRegistry()


@pytest.fixture
def sample_replicas():
    """Sample replica URLs."""
    return [
        "http://email-1:8000",
        "http://email-2:8000",
        "http://email-3:8000",
    ]


# ============================================================================
# TEST: REGISTRATION
# ============================================================================


class TestRegistration:
    """Service registration tests."""

    @pytest.mark.asyncio
    async def test_register_service(self, registry, sample_replicas):
        """Service should be registered with all replicas."""
        await registry.register_service("email_service", sample_replicas)

        assert "email_service" in registry.services
        service = registry.services["email_service"]
        assert len(service.replicas) == 3
        assert all(url in service.replicas for url in sample_replicas)

    @pytest.mark.asyncio
    async def test_register_duplicate_service_raises(self, registry, sample_replicas):
        """Registering same service twice should raise error."""
        await registry.register_service("email_service", sample_replicas)

        with pytest.raises(ValueError, match="already registered"):
            await registry.register_service("email_service", sample_replicas)

    @pytest.mark.asyncio
    async def test_register_empty_replicas_raises(self, registry):
        """Registering with empty replicas should raise error."""
        with pytest.raises(ValueError, match="at least one replica"):
            await registry.register_service("email_service", [])

    @pytest.mark.asyncio
    async def test_register_multiple_services(self, registry):
        """Multiple services should be registerable."""
        await registry.register_service("email_service", ["http://email:8000"])
        await registry.register_service("customer_service", ["http://customer:8000"])

        assert len(registry.services) == 2
        assert "email_service" in registry.services
        assert "customer_service" in registry.services


# ============================================================================
# TEST: SCORING ALGORITHM
# ============================================================================


class TestScoringAlgorithm:
    """ReplicaStats scoring tests."""

    def test_healthy_replica_score(self):
        """Healthy replica should have reasonable score."""
        replica = ReplicaStats(
            url="http://email-1:8000",
            status="HEALTHY",
            latency_ms=50.0,
            error_rate=0.0,
        )

        score = replica.calculate_score()
        assert 0 <= score <= 100
        assert replica.is_healthy()

    def test_unhealthy_replica_worst_score(self):
        """Unhealthy replica should get worst possible score."""
        replica = ReplicaStats(
            url="http://email-1:8000",
            status="UNHEALTHY",
            latency_ms=5000.0,
            error_rate=5.0,
        )

        assert not replica.is_healthy()
        assert replica.calculate_score() == 999.0

    def test_high_latency_increases_score(self):
        """Higher latency should increase score (worse)."""
        replica_fast = ReplicaStats(
            url="http://email-1:8000",
            status="HEALTHY",
            latency_ms=10.0,
            error_rate=0.0,
        )

        replica_slow = ReplicaStats(
            url="http://email-2:8000",
            status="HEALTHY",
            latency_ms=500.0,
            error_rate=0.0,
        )

        assert replica_fast.calculate_score() < replica_slow.calculate_score()

    def test_high_error_rate_increases_score(self):
        """Higher error rate should increase score (worse)."""
        replica_reliable = ReplicaStats(
            url="http://email-1:8000",
            status="HEALTHY",
            latency_ms=50.0,
            error_rate=0.0,
        )

        replica_unreliable = ReplicaStats(
            url="http://email-2:8000",
            status="HEALTHY",
            latency_ms=50.0,
            error_rate=2.0,
        )

        assert replica_reliable.calculate_score() < replica_unreliable.calculate_score()


# ============================================================================
# TEST: ROUTING & SELECTION
# ============================================================================


class TestRouting:
    """Replica selection and routing tests."""

    @pytest.mark.asyncio
    async def test_get_healthiest_returns_best_replica(self, registry):
        """Should return replica with lowest score."""
        await registry.register_service(
            "email_service", ["http://email-1:8000", "http://email-2:8000"]
        )

        # Make first replica faster
        registry.services["email_service"].replicas[
            "http://email-1:8000"
        ].status = "HEALTHY"
        registry.services["email_service"].replicas[
            "http://email-1:8000"
        ].latency_ms = 20.0

        registry.services["email_service"].replicas[
            "http://email-2:8000"
        ].status = "HEALTHY"
        registry.services["email_service"].replicas[
            "http://email-2:8000"
        ].latency_ms = 100.0

        best = registry.get_healthiest("email_service")
        assert best == "http://email-1:8000"

    @pytest.mark.asyncio
    async def test_get_healthiest_skips_unhealthy(self, registry):
        """Should skip unhealthy replicas."""
        await registry.register_service(
            "email_service", ["http://email-1:8000", "http://email-2:8000"]
        )

        # First replica unhealthy
        registry.services["email_service"].replicas[
            "http://email-1:8000"
        ].status = "UNHEALTHY"
        registry.services["email_service"].replicas[
            "http://email-1:8000"
        ].consecutive_failures = 5

        # Second replica healthy
        registry.services["email_service"].replicas[
            "http://email-2:8000"
        ].status = "HEALTHY"
        registry.services["email_service"].replicas[
            "http://email-2:8000"
        ].latency_ms = 50.0

        best = registry.get_healthiest("email_service")
        assert best == "http://email-2:8000"

    @pytest.mark.asyncio
    async def test_get_healthiest_returns_none_if_all_unhealthy(self, registry):
        """Should return None if no healthy replicas."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        registry.services["email_service"].replicas[
            "http://email-1:8000"
        ].status = "UNHEALTHY"

        best = registry.get_healthiest("email_service")
        assert best is None

    @pytest.mark.asyncio
    async def test_get_healthiest_unknown_service_returns_none(self, registry):
        """Should return None for unknown service."""
        best = registry.get_healthiest("nonexistent_service")
        assert best is None


# ============================================================================
# TEST: ERROR TRACKING
# ============================================================================


class TestErrorTracking:
    """Error recording and recovery tests."""

    @pytest.mark.asyncio
    async def test_record_error_increments_failure_count(self, registry):
        """Recording error should increment failure count."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]
        initial_failures = replica.consecutive_failures

        registry.record_error("email_service", "http://email-1:8000")

        assert replica.consecutive_failures == initial_failures + 1

    @pytest.mark.asyncio
    async def test_record_error_increments_error_rate(self, registry):
        """Recording error should increment error rate."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]

        registry.record_error("email_service", "http://email-1:8000")
        assert replica.error_rate > 0.0

    @pytest.mark.asyncio
    async def test_three_failures_marks_unhealthy(self, registry):
        """Three consecutive failures should mark replica unhealthy."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]
        replica.status = "HEALTHY"

        registry.record_error("email_service", "http://email-1:8000")
        registry.record_error("email_service", "http://email-1:8000")
        registry.record_error("email_service", "http://email-1:8000")

        assert replica.status == "UNHEALTHY"

    @pytest.mark.asyncio
    async def test_record_success_resets_failures(self, registry):
        """Recording success should reset failure count."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]
        replica.consecutive_failures = 3

        registry.record_success("email_service", "http://email-1:8000")

        assert replica.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_record_success_decreases_error_rate(self, registry):
        """Recording success should decrease error rate."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]
        replica.error_rate = 2.0

        registry.record_success("email_service", "http://email-1:8000")

        assert replica.error_rate < 2.0


# ============================================================================
# TEST: HEALTH CHECKS
# ============================================================================


class TestHealthChecks:
    """Background health check task tests."""

    @pytest.mark.asyncio
    async def test_start_health_checks(self, registry):
        """Health checks should start and set running flag."""
        await registry.start_health_checks()

        assert registry._health_checker._is_running
        assert registry._health_checker._task is not None

        await registry.stop_health_checks()

    @pytest.mark.asyncio
    async def test_stop_health_checks(self, registry):
        """Health checks should stop gracefully."""
        await registry.start_health_checks()
        await asyncio.sleep(0.1)  # Let it start

        await registry.stop_health_checks()

        assert not registry._health_checker._is_running

    @pytest.mark.asyncio
    async def test_health_check_updates_replica_status(self, registry):
        """Health check should mark replica as healthy."""
        await registry.register_service("email_service", ["http://email-1:8000"])

        replica = registry.services["email_service"].replicas["http://email-1:8000"]
        assert replica.status == "UNKNOWN"

        # Manually run one health check
        await check_replica_health("http://email-1:8000", replica)

        assert replica.status == "HEALTHY"
        assert replica.latency_ms > 0


# ============================================================================
# TEST: SINGLETON PATTERN
# ============================================================================


class TestSingleton:
    """Singleton pattern tests."""

    def test_get_registry_returns_same_instance(self):
        """get_registry() should return same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2
