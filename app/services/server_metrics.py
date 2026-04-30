from __future__ import annotations

import re
from dataclasses import dataclass
from io import StringIO

from app.core.security import decrypt_secret
from app.db.models import Node


class MetricsUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServerMetrics:
    cpu: float
    cpu_cores: int
    load_1: float
    load_5: float
    load_15: float
    tasks: int
    uptime_seconds: int
    services: int
    services_total: int
    ram: float
    ram_used_kb: int
    ram_total_kb: int
    disk: float
    disk_used_kb: int
    disk_total_kb: int


@dataclass(frozen=True)
class DockerContainerInfo:
    id: str
    name: str
    image: str
    status: str
    state: str


@dataclass(frozen=True)
class DockerImageInfo:
    id: str
    repository: str
    tag: str
    size: str
    created_since: str


def collect_node_metrics(node: Node) -> ServerMetrics:
    output = _run_node_command(node, _metrics_command(), timeout=8)
    return _parse_metrics(output)


def collect_node_containers(node: Node) -> list[DockerContainerInfo]:
    output = _run_node_command(node, _containers_command(), timeout=8)
    if "docker_unavailable=" in output:
        raise MetricsUnavailableError(
            "Docker недоступен для пользователя. Добавьте пользователя в группу docker или настройте sudo без пароля для docker."
        )

    containers: list[DockerContainerInfo] = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue

        container_id, name, image, status = [part.strip() for part in parts]
        state = "running" if status.lower().startswith("up") else "stopped"

        containers.append(
            DockerContainerInfo(
                id=container_id,
                name=name,
                image=image,
                status=status,
                state=state,
            )
        )

    return containers


def collect_node_images(node: Node) -> list[DockerImageInfo]:
    output = _run_node_command(node, _images_command(), timeout=8)
    if "docker_unavailable=" in output:
        raise MetricsUnavailableError(
            "Docker недоступен для пользователя. Добавьте пользователя в группу docker или настройте sudo без пароля для docker."
        )

    images: list[DockerImageInfo] = []
    for line in output.splitlines():
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue

        image_id, repository, tag, size, created_since = [part.strip() for part in parts]

        images.append(
            DockerImageInfo(
                id=image_id,
                repository=repository,
                tag=tag,
                size=size,
                created_since=created_since,
            )
        )

    return images


def run_node_container_action(node: Node, container_id: str, action: str) -> str:
    if action not in {"stop", "delete"}:
        raise MetricsUnavailableError("Unsupported container action.")

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container_id):
        raise MetricsUnavailableError("Container id is invalid.")

    docker_action = "stop" if action == "stop" else "rm -f"
    output = _run_node_command(
        node,
        _container_action_command(docker_action, container_id),
        timeout=12,
    )

    if "docker_unavailable=" in output:
        raise MetricsUnavailableError(
            "Docker недоступен для пользователя. Добавьте пользователя в группу docker или настройте sudo без пароля для docker."
        )

    return output.strip()


def collect_node_container_logs(node: Node, container_id: str, tail: int = 300) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container_id):
        raise MetricsUnavailableError("Container id is invalid.")

    safe_tail = min(max(tail, 20), 1000)
    output = _run_node_command(node, _container_logs_command(container_id, safe_tail), timeout=20)
    if "docker_unavailable=" in output:
        raise MetricsUnavailableError(
            "Docker недоступен для пользователя. Добавьте пользователя в группу docker или настройте sudo без пароля для docker."
        )
    return output.rstrip()


def run_node_image_delete(node: Node, image_id: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,191}", image_id):
        raise MetricsUnavailableError("Image id is invalid.")

    output = _run_node_command(node, _image_delete_command(image_id), timeout=30)

    if "docker_unavailable=" in output:
        raise MetricsUnavailableError(
            "Docker недоступен для пользователя. Добавьте пользователя в группу docker или настройте sudo без пароля для docker."
        )

    return output.strip()


def _run_node_command(node: Node, command: str, timeout: int) -> str:
    try:
        import paramiko
    except ImportError as exc:
        raise MetricsUnavailableError("Python package 'paramiko' is not installed.") from exc

    ssh_key = _load_private_key(paramiko, decrypt_secret(node.ssh_key))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=node.server_ip,
            username=node.server_user,
            pkey=ssh_key,
            timeout=6,
            banner_timeout=6,
            auth_timeout=6,
            look_for_keys=False,
            allow_agent=False,
        )

        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()

        output = stdout.read().decode("utf-8", errors="replace")
        error_output = stderr.read().decode("utf-8", errors="replace").strip()

        if exit_code != 0:
            raise MetricsUnavailableError(
                error_output or f"Remote command failed with code {exit_code}."
            )

        return output

    except Exception as exc:
        if isinstance(exc, MetricsUnavailableError):
            raise
        raise MetricsUnavailableError(str(exc)) from exc

    finally:
        client.close()


def _load_private_key(paramiko, value: str):
    errors = []

    for key_class in (
        paramiko.RSAKey,
        paramiko.ECDSAKey,
        paramiko.Ed25519Key,
        paramiko.DSSKey,
    ):
        try:
            return key_class.from_private_key(StringIO(value))
        except Exception as exc:
            errors.append(str(exc))

    raise MetricsUnavailableError("SSH key cannot be parsed: " + "; ".join(errors[-2:]))


def _parse_metrics(output: str) -> ServerMetrics:
    values: dict[str, float] = {}

    for line in output.splitlines():
        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        try:
            values[key] = float(raw_value)
        except ValueError:
            continue

    required = {"cpu", "services", "ram", "disk"}
    missing = required - values.keys()

    if missing:
        raise MetricsUnavailableError(
            "Remote metrics response is incomplete: " + ", ".join(sorted(missing))
        )

    return ServerMetrics(
        cpu=round(_clamp(values["cpu"], 0, 100), 1),
        cpu_cores=max(1, int(round(values.get("cpu_cores", 1)))),
        load_1=round(max(0, values.get("load_1", 0)), 2),
        load_5=round(max(0, values.get("load_5", 0)), 2),
        load_15=round(max(0, values.get("load_15", 0)), 2),
        tasks=max(0, int(round(values.get("tasks", 0)))),
        uptime_seconds=max(0, int(round(values.get("uptime_seconds", 0)))),
        services=max(0, int(round(values["services"]))),
        services_total=max(0, int(round(values.get("services_total", values["services"])))),
        ram=round(_clamp(values["ram"], 0, 100), 1),
        ram_used_kb=max(0, int(round(values.get("ram_used_kb", 0)))),
        ram_total_kb=max(0, int(round(values.get("ram_total_kb", 0)))),
        disk=round(_clamp(values["disk"], 0, 100), 1),
        disk_used_kb=max(0, int(round(values.get("disk_used_kb", 0)))),
        disk_total_kb=max(0, int(round(values.get("disk_total_kb", 0)))),
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _metrics_command() -> str:
    return r"""
set -eu

read_cpu() {
  awk '/^cpu / {print $2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "$10}' /proc/stat
}

calc_cpu() {
  first="$1"
  second="$2"

  set -- $first
  idle1=$4
  total1=0
  for value in "$@"; do
    total1=$((total1 + value))
  done

  set -- $second
  idle2=$4
  total2=0
  for value in "$@"; do
    total2=$((total2 + value))
  done

  diff_idle=$((idle2 - idle1))
  diff_total=$((total2 - total1))

  if [ "$diff_total" -le 0 ]; then
    printf "0"
  else
    awk -v idle="$diff_idle" -v total="$diff_total" 'BEGIN { printf "%.1f", (100 * (total - idle) / total) }'
  fi
}

cpu_a="$(read_cpu)"
sleep 0.4
cpu_b="$(read_cpu)"
cpu="$(calc_cpu "$cpu_a" "$cpu_b")"

cpu_cores="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || printf 1)"

set -- $(awk '{print $1" "$2" "$3}' /proc/loadavg 2>/dev/null || printf "0 0 0")
load_1="${1:-0}"
load_5="${2:-0}"
load_15="${3:-0}"

tasks="$(ps -e --no-headers 2>/dev/null | wc -l | tr -d ' ' || printf 0)"
uptime_seconds="$(cut -d. -f1 /proc/uptime 2>/dev/null || printf 0)"

services_total=0
if command -v docker >/dev/null 2>&1 && docker ps -q >/dev/null 2>&1; then
  services="$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
  services_total="$(docker ps -aq 2>/dev/null | wc -l | tr -d ' ')"
elif command -v sudo >/dev/null 2>&1 && sudo -n docker ps -q >/dev/null 2>&1; then
  services="$(sudo -n docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
  services_total="$(sudo -n docker ps -aq 2>/dev/null | wc -l | tr -d ' ')"
else
  services="$(systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null | wc -l | tr -d ' ' || printf 0)"
  services_total="$(systemctl list-units --type=service --all --no-legend --no-pager 2>/dev/null | wc -l | tr -d ' ' || printf 0)"
fi

ram_values="$(awk '
  /MemTotal/ {total=$2}
  /MemAvailable/ {available=$2}
  END {
    used=total-available
    if (total > 0) {
      printf "%.1f %d %d\n", (100 * used / total), used, total
    } else {
      printf "0 0 0\n"
    }
  }
' /proc/meminfo 2>/dev/null || printf "0 0 0")"

set -- ${ram_values:-0 0 0}
ram="${1:-0}"
ram_used_kb="${2:-0}"
ram_total_kb="${3:-0}"

disk_values="$(df -Pk / 2>/dev/null | awk '
  NR==2 {
    percent=$5
    gsub(/%/, "", percent)
    printf "%s %s %s\n", percent, $3, $2
  }
' || printf "0 0 0")"

set -- ${disk_values:-0 0 0}
disk="${1:-0}"
disk_used_kb="${2:-0}"
disk_total_kb="${3:-0}"

printf "cpu=%s\ncpu_cores=%s\nload_1=%s\nload_5=%s\nload_15=%s\ntasks=%s\nuptime_seconds=%s\nservices=%s\nservices_total=%s\nram=%s\nram_used_kb=%s\nram_total_kb=%s\ndisk=%s\ndisk_used_kb=%s\ndisk_total_kb=%s\n" "$cpu" "$cpu_cores" "$load_1" "$load_5" "$load_15" "$tasks" "$uptime_seconds" "$services" "$services_total" "$ram" "$ram_used_kb" "$ram_total_kb" "$disk" "$disk_used_kb" "$disk_total_kb"
"""


def _containers_command() -> str:
    return r"""
set -eu

docker_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then
    docker_cmd="docker"
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
fi

if [ -z "$docker_cmd" ]; then
  echo "docker_unavailable=permission_denied_or_not_installed"
  exit 0
fi

$docker_cmd ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}'
"""


def _images_command() -> str:
    return r"""
set -eu

docker_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker images --format '{{.ID}}' >/dev/null 2>&1; then
    docker_cmd="docker"
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker images --format '{{.ID}}' >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
fi

if [ -z "$docker_cmd" ]; then
  echo "docker_unavailable=permission_denied_or_not_installed"
  exit 0
fi

$docker_cmd images --format '{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}|{{.CreatedSince}}'
"""


def _container_action_command(docker_action: str, container_id: str) -> str:
    return f"""
set -eu

docker_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker ps -a --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="docker"
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker ps -a --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
fi

if [ -z "$docker_cmd" ]; then
  echo "docker_unavailable=permission_denied_or_not_installed"
  exit 0
fi

$docker_cmd {docker_action} {container_id}
"""


def _container_logs_command(container_id: str, tail: int) -> str:
    return f"""
set -eu

docker_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker ps -a --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="docker"
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker ps -a --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
fi

if [ -z "$docker_cmd" ]; then
  echo "docker_unavailable=permission_denied_or_not_installed"
  exit 0
fi

$docker_cmd logs --tail {tail} --timestamps {container_id} 2>&1
"""


def _image_delete_command(image_id: str) -> str:
    return f"""
set -eu

docker_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker images --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="docker"
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker images --format '{{{{.ID}}}}' >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
fi

if [ -z "$docker_cmd" ]; then
  echo "docker_unavailable=permission_denied_or_not_installed"
  exit 0
fi

$docker_cmd rmi -f {image_id}
"""
