from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool, text

from alembic import context

# Import our app config
from src.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We aren't using autogenerate for tenant tables, they are managed via raw SQL
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode across all tenant schemas."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Check for specific tenant passed via -x tenant=tenant_id
    x_args = context.get_x_argument(as_dictionary=True)
    specific_schema = x_args.get("tenant_schema")

    with connectable.connect() as connection:
        if specific_schema:
            schemas = [specific_schema]
        else:
            # Find all tenant schemas using information_schema
            result = connection.execute(text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
            ))
            schemas = [row[0] for row in result]
        
        for schema in schemas:
            print(f"--- Running migrations for schema: {schema} ---")
            
            # Set search path so unqualified tables go into this schema
            connection.execute(text(f"SET search_path TO {schema}, public"))

            # Configure context for this specific schema's version table
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table_schema=schema,
            )

            with context.begin_transaction():
                context.run_migrations()
            
            # Explicitly commit the connection just to be absolutely sure
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
