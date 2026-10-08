from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

config = context.config
target_metadata = Base.metadata

# The app passes its own connection when it migrates a per-process test schema.
connection = config.attributes.get("connection")

if connection is None and config.config_file_name:
    fileConfig(config.config_file_name)


def run(conn) -> None:
    context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
elif connection is not None:
    run(connection)
else:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        run(conn)
        conn.commit()
    engine.dispose()
