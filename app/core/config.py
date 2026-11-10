from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # MCP Client (seperate MCP service)
    MCP_SERVER_URL: str
    MCP_REQUEST_TIMEOUT_SECONDS: int = Field(default=10, gt=0, le=300)
    POSTGRES_MCP_URL: str = "http://127.0.0.1:8001/mcp"
    POSTGRES_MCP_TOKEN: SecretStr | None = Field(default=None, min_length=32)
    EMAIL_MCP_URL: str | None = None
    EMAIL_MCP_TOKEN: SecretStr | None = Field(default=None, min_length=32)
    EMAIL_MCP_TIMEOUT_SECONDS: int = Field(default=10, gt=0, le=60)
    OPERATOR_API_TOKEN: SecretStr | None = Field(default=None, min_length=32)
    MAX_WORKFLOWS_PER_BATCH: int = Field(default=10, ge=1, le=1000)
    DELIVERY_CONCURRENCY: int = Field(default=2, ge=1, le=50)
    DELIVERY_RATE_COUNT: int = Field(default=5, ge=1, le=1000)
    DELIVERY_RATE_WINDOW_SECONDS: float = Field(
        default=60, ge=1, le=3600, allow_inf_nan=False
    )
    DELIVERY_LIMIT_MODE: Literal["disabled", "single_worker_exclusive"] = "disabled"
    POSTGRES_READ_RETRY_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    POSTGRES_READ_RETRY_BUDGET_SECONDS: float = Field(
        default=20, ge=1, le=60, allow_inf_nan=False
    )
    POSTGRES_READ_RETRY_INITIAL_SECONDS: float = Field(
        default=0.25, gt=0, allow_inf_nan=False
    )
    POSTGRES_READ_RETRY_MAX_SECONDS: float = Field(default=2, gt=0, allow_inf_nan=False)

    OPENAI_API_KEY: str
    RESEND_API_KEY: str
    SENDER_EMAIL: str
    MAX_RETRIES: int

    # LLM Models:
    GENERATOR_MODEL: str = "gpt-4-turbo"
    CRITIC_MODEL: str = "gpt-4"
    REFINER_MODEL: str = "gpt-3.5-turbo"

    # LangSmith (Tracing)
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str
    LANGSMITH_ENABLED: bool = True

    # FastAPI Server Configuration
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS Configuration
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # configuration to load from .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_read_retry_backoff(self) -> "Settings":
        """Ensure retry backoff is bounded by the overall read budget."""
        if not (
            self.POSTGRES_READ_RETRY_INITIAL_SECONDS
            <= self.POSTGRES_READ_RETRY_MAX_SECONDS
            <= self.POSTGRES_READ_RETRY_BUDGET_SECONDS
        ):
            raise ValueError("Invalid PostgreSQL read retry backoff limits")
        return self


settings = Settings()


# ============================================================================
# MCP REGISTRY INITIALIZATION
# ============================================================================


async def _register_all_services(registry) -> None:
    """Register all MCP services with the registry."""
    from app.mcp.config import (
        get_email_service_replicas,
        get_customer_service_replicas,
        get_workflow_service_replicas,
        get_escalation_service_replicas,
        get_metrics_service_replicas,
    )

    services = [
        ("email_service", get_email_service_replicas()),
        ("customer_service", get_customer_service_replicas()),
        ("workflow_service", get_workflow_service_replicas()),
        ("escalation_service", get_escalation_service_replicas()),
        ("metrics_service", get_metrics_service_replicas()),
    ]

    for name, replicas in services:
        await registry.register_service(name=name, replicas=replicas)


async def initialize_mcp_registry() -> None:
    """
    Initialize MCPRegistry and register all services.

    Call this during application startup.
    """
    from app.mcp.registry import get_registry

    registry = get_registry()
    await _register_all_services(registry)
    await registry.start_health_checks()
