from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Base, User, UserType
from app.db.session import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    _ensure_project_node_links()
    _ensure_pipeline_project_links()

    with Session(engine) as db:
        owner = db.scalar(select(User).where(User.username == "owner"))
        if owner is None:
            db.add(
                User(
                    username="owner",
                    rsa_password=hash_password("owner"),
                    user_type=UserType.OWNER,
                )
            )
            db.commit()


def _ensure_sqlite_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if not inspector.has_table("nodes"):
        return

    columns = {column["name"] for column in inspector.get_columns("nodes")}
    with engine.begin() as connection:
        if "status" not in columns:
            connection.execute(text("ALTER TABLE nodes ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'down'"))
        if "project_id" not in columns:
            connection.execute(text("ALTER TABLE nodes ADD COLUMN project_id INTEGER REFERENCES projects(id)"))

    if inspector.has_table("tasks"):
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        with engine.begin() as connection:
            if "scheduled_at" not in task_columns:
                connection.execute(text("ALTER TABLE tasks ADD COLUMN scheduled_at DATETIME"))
            if "pipeline_id" not in task_columns:
                connection.execute(text("ALTER TABLE tasks ADD COLUMN pipeline_id INTEGER REFERENCES pipelines(id)"))

    if inspector.has_table("ansible_playbooks"):
        playbook_columns = {column["name"] for column in inspector.get_columns("ansible_playbooks")}
        with engine.begin() as connection:
            if "run_command" not in playbook_columns:
                connection.execute(
                    text(
                        "ALTER TABLE ansible_playbooks ADD COLUMN run_command VARCHAR(500) "
                        "NOT NULL DEFAULT 'ansible-playbook -i {inventory} {playbook}'"
                    )
                )


def _ensure_project_node_links() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if not inspector.has_table("nodes") or not inspector.has_table("project_nodes"):
        return

    node_columns = {column["name"] for column in inspector.get_columns("nodes")}
    if "project_id" not in node_columns:
        return

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, project_id FROM nodes WHERE project_id IS NOT NULL")).fetchall()
        for node_id, project_id in rows:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO project_nodes (project_id, node_id, created_at) "
                    "VALUES (:project_id, :node_id, CURRENT_TIMESTAMP)"
                ),
                {"project_id": project_id, "node_id": node_id},
            )


def _ensure_pipeline_project_links() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if not inspector.has_table("pipelines") or not inspector.has_table("pipeline_projects"):
        return

    pipeline_columns = {column["name"] for column in inspector.get_columns("pipelines")}
    if "project_id" not in pipeline_columns:
        return

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, project_id FROM pipelines WHERE project_id IS NOT NULL")).fetchall()
        for pipeline_id, project_id in rows:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO pipeline_projects (pipeline_id, project_id, created_at) "
                    "VALUES (:pipeline_id, :project_id, CURRENT_TIMESTAMP)"
                ),
                {"pipeline_id": pipeline_id, "project_id": project_id},
            )
