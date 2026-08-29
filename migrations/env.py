"""Alembic environment for OpenTrading.

The target DSN comes from the application settings (``OT_POSTGRES_DSN``; the
default matches the local docker-compose dev stack). Migrations are
hand-written SQLAlchemy operations — there is no declarative ``target_metadata``:
domain tables are introduced per phase, each in its own migration.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from core.config.settings import ensure_psycopg_dsn, get_settings
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Least privilege (ADR-0025): migrations run as the DDL-capable migrator role
# when one is configured; otherwise (dev) the app DSN doubles as both.
config.set_main_option(
    "sqlalchemy.url",
    ensure_psycopg_dsn(settings.postgres_migrator_dsn or settings.postgres_dsn).replace("%", "%%"),
)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
