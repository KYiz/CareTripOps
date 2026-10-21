from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base


config = context.config
# Tests may pass a throwaway database through config.attributes; otherwise use the app setting.
database_url = config.attributes.get("database_url") or settings.database_url
config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # LangGraph's AsyncPostgresSaver owns its checkpoint tables; Alembic must not manage them.
    return not (type_ == "table" and name.startswith("checkpoint"))


def run_migrations_offline():
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True,
                      include_name=include_name)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
