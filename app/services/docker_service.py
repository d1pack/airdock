from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config import settings


class DockerUnavailableError(RuntimeError):
    """Raised when Docker cannot be reached from the application."""


@dataclass(frozen=True)
class ContainerInfo:
    id: str
    name: str
    image: str
    status: str
    state: str
    created_at: datetime | None


class DockerService:
    def __init__(self) -> None:
        try:
            import docker
            from docker.errors import DockerException
        except ImportError as exc:
            raise DockerUnavailableError(
                "Python package 'docker' is not installed."
            ) from exc

        self._docker_exception = DockerException
        try:
            if settings.docker_base_url:
                self._client = docker.DockerClient(base_url=settings.docker_base_url)
            else:
                self._client = docker.from_env()
            self._client.ping()
        except DockerException as exc:
            raise DockerUnavailableError(str(exc)) from exc

    def list_containers(self, all_containers: bool = True) -> list[ContainerInfo]:
        try:
            containers = self._client.containers.list(all=all_containers)
        except self._docker_exception as exc:
            raise DockerUnavailableError(str(exc)) from exc

        return [self._container_info(container) for container in containers]

    @staticmethod
    def _container_info(container: Any) -> ContainerInfo:
        attrs = container.attrs or {}
        config = attrs.get("Config") or {}
        created_at = _parse_docker_datetime(attrs.get("Created"))

        return ContainerInfo(
            id=container.short_id,
            name=container.name,
            image=", ".join(config.get("Image", "").splitlines()) or "unknown",
            status=container.status,
            state=(attrs.get("State") or {}).get("Status", container.status),
            created_at=created_at,
        )


def _parse_docker_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
