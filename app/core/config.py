from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    DB_MAX_POOL_SIZE: int
    DB_MIN_POOL_SIZE: int
    DB_MAX_OVERFLOW: int
    DB_POOL_TIMEOUT: int
    DB_POOL_RECYCLE: int

    DB_RETRY_ATTEMPTS: int
    DB_RETRY_MIN_WAIT: int
    DB_RETRY_MAX_WAIT: int
    DB_RETRY_MULTIPLIER: int

    # MCP Client (seperate MCP service)
    MCP_SERVER_URL: str
    MCP_REQUEST_TIMEOUT_SECONDS: int = 10

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

    # configuration to load from .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
