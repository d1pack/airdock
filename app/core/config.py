from dataclasses import dataclass
from os import getenv


def _env_bool(name: str, default: bool = False) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = getenv("AIRDOCK_APP_NAME", "Airdock")
    debug: bool = _env_bool("AIRDOCK_DEBUG", True)
    docker_base_url: str | None = getenv("AIRDOCK_DOCKER_BASE_URL")
    database_url: str = getenv("AIRDOCK_DATABASE_URL", "sqlite:///./airdock.db")
    secret_key: str = getenv("AIRDOCK_SECRET_KEY", "change-this-local-dev-secret")
    access_token_minutes: int = int(getenv("AIRDOCK_ACCESS_TOKEN_MINUTES", str(60 * 24 * 30)))
    refresh_token_days: int = int(getenv("AIRDOCK_REFRESH_TOKEN_DAYS", "90"))
    playbook_timeout_seconds: int = int(getenv("AIRDOCK_PLAYBOOK_TIMEOUT_SECONDS", "7200"))


settings = Settings()
