import re
import shlex
import time
from dataclasses import dataclass
from io import StringIO
from typing import Callable

from app.core.security import decrypt_secret
from app.db.models import AnsiblePlaybook, Node, Project


class AnsibleRunError(RuntimeError):
    pass


class AnsibleRunCancelled(AnsibleRunError):
    pass


@dataclass(frozen=True)
class AnsibleRunResult:
    status: str
    output: str
    return_code: int
    node_id: int
    node_name: str
    remote_path: str


def run_playbook(playbook: AnsiblePlaybook, project: Project, nodes: list[Node], should_stop: Callable[[], bool] | None = None) -> AnsibleRunResult:
    if not nodes:
        raise AnsibleRunError("В проекте нет курьеров для запуска playbook.")

    ordered_nodes = sorted(nodes, key=lambda node: 0 if node.status == "up" else 1)
    errors: list[str] = []
    for node in ordered_nodes:
        if should_stop and should_stop():
            raise AnsibleRunCancelled("Запуск playbook остановлен пользователем.")
        try:
            return _run_playbook_on_node(playbook, project, node, should_stop=should_stop)
        except AnsibleRunError as exc:
            errors.append(f"{node.name}: {exc}")

    raise AnsibleRunError("Нет доступного курьера для запуска playbook: " + "; ".join(errors))


def _run_playbook_on_node(playbook: AnsiblePlaybook, project: Project, node: Node, should_stop: Callable[[], bool] | None = None) -> AnsibleRunResult:
    try:
        import paramiko
    except ImportError as exc:
        raise AnsibleRunError("Python package 'paramiko' is not installed.") from exc

    ssh_key = _load_private_key(paramiko, decrypt_secret(node.ssh_key))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    project_dir = _safe_path_part(project.name, fallback=f"project_{project.id}")
    playbook_file = _playbook_file_name(playbook)
    remote_dir = f"/home/{node.server_user}/airdock/{project_dir}"
    remote_playbook_path = f"{remote_dir}/{playbook_file}"
    remote_inventory_path = f"{remote_dir}/inventory.ini"

    try:
        client.connect(
            hostname=node.server_ip,
            username=node.server_user,
            pkey=ssh_key,
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
            look_for_keys=False,
            allow_agent=False,
        )
        _exec(client, f"mkdir -p {shlex.quote(remote_dir)}", timeout=12, should_stop=should_stop)

        sftp = client.open_sftp()
        try:
            with sftp.file(remote_playbook_path, "w") as remote_file:
                remote_file.write(playbook.content)
            with sftp.file(remote_inventory_path, "w") as inventory_file:
                inventory_file.write("[airdock]\nlocalhost ansible_connection=local\n")
            for file in playbook.files:
                remote_file_path = _remote_extra_file_path(remote_dir, file.path)
                remote_file_dir = remote_file_path.rsplit("/", 1)[0]
                _exec(client, f"mkdir -p {shlex.quote(remote_file_dir)}", timeout=12, should_stop=should_stop)
                with sftp.file(remote_file_path, "w") as extra_file:
                    extra_file.write(file.content)
        finally:
            sftp.close()

        command = f"cd {shlex.quote(remote_dir)} && {_render_run_command(playbook, remote_playbook_path, remote_inventory_path)}"
        output, return_code = _exec(client, command, timeout=900, allow_failed=True, should_stop=should_stop)
        return AnsibleRunResult(
            status="success" if return_code == 0 else "failed",
            output=output.strip()[-20000:],
            return_code=return_code,
            node_id=node.id,
            node_name=node.name,
            remote_path=remote_playbook_path,
        )
    except Exception as exc:
        if isinstance(exc, AnsibleRunError):
            raise
        raise AnsibleRunError(str(exc)) from exc
    finally:
        client.close()


def _exec(client, command: str, timeout: int, allow_failed: bool = False, should_stop: Callable[[], bool] | None = None) -> tuple[str, int]:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    channel = stdout.channel
    started_at = time.monotonic()
    while not channel.exit_status_ready():
        if should_stop and should_stop():
            channel.close()
            raise AnsibleRunCancelled("Запуск playbook остановлен пользователем.")
        if time.monotonic() - started_at > timeout:
            channel.close()
            raise AnsibleRunError(f"Remote command timed out after {timeout} seconds.")
        time.sleep(0.25)
    return_code = channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace")
    error_output = stderr.read().decode("utf-8", errors="replace")
    combined = output + ("\n" + error_output if error_output else "")
    if return_code != 0 and not allow_failed:
        raise AnsibleRunError(combined.strip() or f"Remote command failed with code {return_code}.")
    return combined, return_code


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
    raise AnsibleRunError("SSH key cannot be parsed: " + "; ".join(errors[-2:]))


def _playbook_file_name(playbook: AnsiblePlaybook) -> str:
    name = _safe_path_part(playbook.name, fallback=f"playbook_{playbook.id}")
    if name.endswith((".yml", ".yaml")):
        return name
    return name + ".yml"


def _render_run_command(playbook: AnsiblePlaybook, remote_playbook_path: str, remote_inventory_path: str) -> str:
    template = (playbook.run_command or "").strip() or "ansible-playbook -i {inventory} {playbook}"
    return (
        template
        .replace("{inventory}", shlex.quote(remote_inventory_path))
        .replace("{playbook}", shlex.quote(remote_playbook_path))
        .replace("{playbook_file}", shlex.quote(remote_playbook_path.rsplit("/", 1)[-1]))
    )


def _remote_extra_file_path(remote_dir: str, path: str) -> str:
    safe_parts = []
    for part in path.replace("\\", "/").split("/"):
        if not part or part in {".", ".."}:
            continue
        safe_part = _safe_file_path_part(part)
        if safe_part:
            safe_parts.append(safe_part)
    if not safe_parts:
        raise AnsibleRunError("Playbook file path is empty.")
    return remote_dir.rstrip("/") + "/" + "/".join(safe_parts)


def _safe_file_path_part(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip())[:120].strip()


def _safe_path_part(value: str, fallback: str = "playbook") -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("._-")
    return safe[:80] or fallback
