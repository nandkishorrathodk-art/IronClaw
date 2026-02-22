"""
Ironclaw Configuration Management
Optimized for Acer Swift Neo (16GB RAM, Intel NPU)
"""
from functools import lru_cache
from typing import Literal, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # API Server
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = True
    api_workers: int = 1
    secret_key: str = Field(..., min_length=32)
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    # Database
    database_url: str = Field(
        ..., description="PostgreSQL connection URL with asyncpg driver"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    redis_cache_ttl: int = 3600

    # Qdrant Vector DB
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_conversations: str = "ironclaw_conversations"
    qdrant_collection_knowledge: str = "ironclaw_knowledge"

    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model_fast: str = "gpt-3.5-turbo"
    openai_model_smart: str = "gpt-4-turbo-preview"
    openai_model_vision: str = "gpt-4-vision-preview"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.7

    # Anthropic
    anthropic_api_key: Optional[str] = None
    anthropic_model_fast: str = "claude-3-haiku-20240307"
    anthropic_model_smart: str = "claude-3-opus-20240229"
    anthropic_max_tokens: int = 4096
    anthropic_temperature: float = 0.7

    # Google Gemini
    google_api_key: Optional[str] = None
    google_model_fast: str = "gemini-1.5-flash"
    google_model_smart: str = "gemini-1.5-pro"
    google_max_tokens: int = 4096
    google_temperature: float = 0.7

    # Groq
    groq_api_key: Optional[str] = None
    groq_model_fast: str = "llama-3.1-8b-instant"
    groq_model_smart: str = "llama-3.1-70b-versatile"
    groq_max_tokens: int = 4096
    groq_temperature: float = 0.7

    # Local AI (Intel NPU)
    enable_local_ai: bool = True
    local_model_path: str = "models/phi-3-mini-4k-instruct"
    local_model_name: str = "phi-3-mini"
    local_device: Literal["NPU", "CPU", "GPU"] = "NPU"
    local_precision: Literal["FP32", "FP16", "INT8"] = "INT8"
    local_max_tokens: int = 2048
    local_temperature: float = 0.7

    # AI Router
    router_default_provider: Literal["openai", "anthropic", "google", "groq", "local"] = (
        "groq"
    )
    router_enable_learning: bool = True
    router_enable_cost_tracking: bool = True
    router_max_cost_per_day_usd: float = 10.0
    router_task_conversation: str = "groq"
    router_task_code_generation: str = "openai"
    router_task_reasoning: str = "anthropic"
    router_task_vision: str = "openai"
    router_task_privacy: str = "local"

    # Performance & Resource Limits
    max_concurrent_requests: int = 100
    request_timeout_seconds: int = 120
    max_memory_mb: int = 8192  # 8GB limit for 16GB total RAM
    enable_memory_monitoring: bool = True
    memory_warning_threshold_mb: int = 7168  # Warn at 7GB

    # Monitoring
    enable_prometheus: bool = True
    prometheus_port: int = 9090
    enable_tracing: bool = True
    tracing_endpoint: str = "http://localhost:4318"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Security
    enable_authentication: bool = True
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours
    enable_rate_limiting: bool = True
    rate_limit_per_minute: int = 60

    # Features
    enable_vision: bool = True
    enable_voice: bool = True
    enable_automation: bool = False
    enable_security_scanning: bool = False
    enable_plugins: bool = True

    # Development
    enable_swagger_ui: bool = True
    enable_redoc: bool = True
    enable_cors: bool = True

    @validator("allowed_origins")
    def parse_allowed_origins(cls, v: str) -> list[str]:
        """Parse comma-separated origins into list."""
        return [origin.strip() for origin in v.split(",")]

    @validator("secret_key", "jwt_secret_key")
    def validate_secret_keys(cls, v: str, field: str) -> str:
        """Ensure secret keys are strong in production."""
        if len(v) < 32:
            raise ValueError(f"{field.name} must be at least 32 characters")
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL (for Alembic migrations)."""
        return self.database_url.replace("+asyncpg", "").replace("postgresql+asyncpg://", "postgresql://")

    @property
    def available_ai_providers(self) -> list[str]:
        """Get list of configured AI providers."""
        providers = []
        if self.openai_api_key:
            providers.append("openai")
        if self.anthropic_api_key:
            providers.append("anthropic")
        if self.google_api_key:
            providers.append("google")
        if self.groq_api_key:
            providers.append("groq")
        if self.enable_local_ai:
            providers.append("local")
        return providers

    def get_model_for_task(self, task_type: str) -> str:
        """Get configured model for specific task type."""
        task_mapping = {
            "conversation": self.router_task_conversation,
            "code_generation": self.router_task_code_generation,
            "reasoning": self.router_task_reasoning,
            "vision": self.router_task_vision,
            "privacy": self.router_task_privacy,
        }
        return task_mapping.get(task_type, self.router_default_provider)


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Export for convenience
settings = get_settings()
