"""Engine and sessions. In test, each process gets its own Postgres schema."""

import secrets
import time
from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
STALE_SCHEMA_SECONDS = 24 * 3600


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.schema: str | None = None
        connect_args = {}
        if settings.env == "test":
            # Needs a direct connection: poolers like PgBouncer drop startup options.
            self.schema = f"run_{secrets.token_hex(6)}"
            connect_args["options"] = f"-csearch_path={self.schema}"
        self.engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        """Test only: drop schemas left by killed runs, then create and migrate ours."""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT nspname, obj_description(oid, 'pg_namespace') FROM pg_namespace "
                    "WHERE nspname LIKE 'run\\_%'"
                )
            )
            for name, created in rows.all():
                if created and created.isdigit() and time.time() - int(created) > STALE_SCHEMA_SECONDS:
                    conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            conn.execute(text(f"COMMENT ON SCHEMA \"{self.schema}\" IS '{int(time.time())}'"))
        self.migrate()

    def migrate(self) -> None:
        cfg = alembic_config()
        with self.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")

    def drop_schema(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))

    def close(self) -> None:
        if self.schema:
            self.drop_schema()
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.db.sessions() as session:
        yield session
