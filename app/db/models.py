from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserType(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"

    @property
    def label(self) -> str:
        labels = {
            self.OWNER: "Владелец",
            self.ADMIN: "Администратор",
            self.USER: "Пользователь",
        }
        return labels[self]

    @property
    def can_manage(self) -> bool:
        return self in {self.OWNER, self.ADMIN}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    rsa_password: Mapped[str] = mapped_column(String(256))
    user_type: Mapped[UserType] = mapped_column(Enum(UserType), default=UserType.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")
    project_access: Mapped[list["ProjectUser"]] = relationship(back_populates="user")


class ProjectNode(Base):
    __tablename__ = "project_nodes"
    __table_args__ = (UniqueConstraint("project_id", "node_id", name="uq_project_nodes_project_node"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="node_links")
    node: Mapped["Node"] = relationship(back_populates="project_links")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("server_ip", name="uq_nodes_server_ip"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="truck")
    status: Mapped[str] = mapped_column(String(16), default="down")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    server_ip: Mapped[str] = mapped_column(String(64), index=True)
    server_user: Mapped[str] = mapped_column(String(80))
    ssh_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project_links: Mapped[list[ProjectNode]] = relationship(back_populates="node", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(secondary="project_nodes", back_populates="nodes", viewonly=True)
    containers: Mapped[list["ProjectContainer"]] = relationship(back_populates="node")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped[User] = relationship()
    users: Mapped[list["ProjectUser"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    node_links: Mapped[list[ProjectNode]] = relationship(back_populates="project", cascade="all, delete-orphan")
    nodes: Mapped[list[Node]] = relationship(secondary="project_nodes", back_populates="projects", viewonly=True)
    containers: Mapped[list["ProjectContainer"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    ansible_playbooks: Mapped[list["AnsiblePlaybook"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    pipelines: Mapped[list["Pipeline"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    @property
    def icon(self) -> str:
        return self.name[:3].upper()

    @property
    def status(self) -> str:
        return "active" if any(node.status == "up" for node in self.nodes) else "inactive"

    @property
    def status_label(self) -> str:
        return "Активен" if self.status == "active" else "Не активен"


class ProjectUser(Base):
    __tablename__ = "project_users"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_users_project_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="users")
    user: Mapped[User] = relationship(back_populates="project_access")


class ProjectContainer(Base):
    __tablename__ = "project_containers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    container_id: Mapped[str] = mapped_column(String(120), default="")
    container_name: Mapped[str] = mapped_column(String(160))
    image: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="containers")
    node: Mapped[Node] = relationship(back_populates="containers")


class PipelineProject(Base):
    __tablename__ = "pipeline_projects"
    __table_args__ = (UniqueConstraint("pipeline_id", "project_id", name="uq_pipeline_projects_pipeline_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="project_links")
    project: Mapped[Project] = relationship()


class AnsiblePlaybook(Base):
    __tablename__ = "ansible_playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    run_command: Mapped[str] = mapped_column(String(500), default="ansible-playbook -i {inventory} {playbook}")
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_output: Mapped[str] = mapped_column(Text, default="")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="ansible_playbooks")
    files: Mapped[list["AnsiblePlaybookFile"]] = relationship(back_populates="playbook", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="playbook")


class AnsiblePlaybookFile(Base):
    __tablename__ = "ansible_playbook_files"
    __table_args__ = (UniqueConstraint("playbook_id", "path", name="uq_ansible_playbook_files_playbook_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playbook_id: Mapped[int] = mapped_column(ForeignKey("ansible_playbooks.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    playbook: Mapped[AnsiblePlaybook] = relationship(back_populates="files")


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    principles: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    project: Mapped[Project] = relationship(back_populates="pipelines")
    project_links: Mapped[list[PipelineProject]] = relationship(back_populates="pipeline", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship(secondary="pipeline_projects", viewonly=True)
    steps: Mapped[list["PipelineStep"]] = relationship(back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineStep.position")


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    playbook_id: Mapped[int] = mapped_column(ForeignKey("ansible_playbooks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pipeline: Mapped[Pipeline] = relationship(back_populates="steps")
    playbook: Mapped[AnsiblePlaybook] = relationship()


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="info", index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    project: Mapped[Project | None] = relationship()
    node: Mapped[Node | None] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(80), default="system")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    playbook_id: Mapped[int | None] = mapped_column(ForeignKey("ansible_playbooks.id", ondelete="SET NULL"), nullable=True, index=True)
    pipeline_id: Mapped[int | None] = mapped_column(ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped[User | None] = relationship()
    project: Mapped[Project | None] = relationship()
    node: Mapped[Node | None] = relationship()
    playbook: Mapped[AnsiblePlaybook | None] = relationship(back_populates="tasks")
    pipeline: Mapped[Pipeline | None] = relationship()

    @property
    def owner_label(self) -> str:
        return self.owner.username if self.owner else self.owner_name

    @property
    def scheduled_at_msk(self) -> datetime | None:
        return self.scheduled_at + timedelta(hours=3) if self.scheduled_at else None

    @property
    def scheduled_at_msk_value(self) -> str:
        value = self.scheduled_at_msk
        return value.strftime("%Y-%m-%dT%H:%M") if value else ""

    @property
    def status_label(self) -> str:
        labels = {
            "draft": "Ожидание запуска",
            "scheduled": "Ожидание запуска",
            "queued": "Ожидание запуска",
            "running": "Выполняется",
            "cancel_requested": "Остановка задачи",
            "cancelled": "Задача остановлена",
            "success": "Задача выполнилась",
            "failed": "Ошибка выполнения задачи",
        }
        return labels.get(self.status, self.status)

    @property
    def status_tone(self) -> str:
        if self.status == "success":
            return "success"
        if self.status == "failed":
            return "error"
        if self.status == "cancelled":
            return "error"
        return "waiting"


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")
