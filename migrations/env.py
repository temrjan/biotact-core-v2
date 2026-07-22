"""Alembic environment configuration."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, make_url, pool

from biotact.core.config import get_settings
from biotact.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging. ``disable_existing_loggers``
# defaults to True, which switches off every logger already created — including
# ``biotact.modules.hr``. Harmless for a standalone ``alembic upgrade``, but in
# the test process it silently kills the HR log assertions of every test that
# runs after a migration test.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Set the SQLAlchemy URL. Tests and CI point everything at DATABASE_URL (async);
# honor it here so Alembic targets the SAME database rather than the settings
# defaults — a mismatch fails migrations with an auth / wrong-database error.
# Alembic uses a sync driver, so swap the async driver for psycopg2.
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    _sync_url = make_url(_database_url).set(drivername="postgresql+psycopg2")
    config.set_main_option(
        "sqlalchemy.url", _sync_url.render_as_string(hide_password=False)
    )
else:
    config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)

# Model's MetaData for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
