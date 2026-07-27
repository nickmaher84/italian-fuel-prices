from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from alembic.operations import Operations

from app.core import app as flask_app, db
import app.db.models  # noqa: F401  -- register models on db.metadata


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use the same database URL the Flask app resolves at runtime. Flask-SQLAlchemy
# rebases relative SQLite paths onto the instance folder, so deriving the URL
# from the live app keeps migrations and the app pointed at the same file.
with flask_app.app_context():
    config.set_main_option(
        "sqlalchemy.url", db.engine.url.render_as_string(hide_password=False)
    )

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = db.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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


def _is_partitioned_table_or_child(table_name: str) -> bool:
    """Check if a table is partitioned or a child partition of a partitioned table."""
    partitioned_tables = {
        table.name for table in target_metadata.tables.values()
        if 'partition_by' in table.info
    }

    if table_name in partitioned_tables:
        return True

    for parent in partitioned_tables:
        if table_name.startswith(parent + '_'):
            return True

    return False


def process_revision_directives(context, revision, directives):
    """Filter out migration directives that would alter partitioned tables."""
    for directive in directives:
        if directive.upgrade_ops:
            filtered_ops = []
            for op in directive.upgrade_ops.ops:
                table_name = getattr(op, 'table_name', None)
                if table_name and _is_partitioned_table_or_child(table_name):
                    continue
                filtered_ops.append(op)
            directive.upgrade_ops.ops = filtered_ops

        if directive.downgrade_ops:
            filtered_ops = []
            for op in directive.downgrade_ops.ops:
                table_name = getattr(op, 'table_name', None)
                if table_name and _is_partitioned_table_or_child(table_name):
                    continue
                filtered_ops.append(op)
            directive.downgrade_ops.ops = filtered_ops


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
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
