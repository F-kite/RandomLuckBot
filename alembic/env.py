from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bot.models import Base
from dotenv import load_dotenv

load_dotenv()

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

# Используем DATABASE_URL из переменных окружения
database_url = os.getenv('DATABASE_URL')
if database_url:
    config.set_main_option('sqlalchemy.url', database_url)
else:
    # Fallback для случаев, когда DATABASE_URL не установлен
    print("Warning: DATABASE_URL not found in environment variables")

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()

# Не вызываем функции автоматически при импорте
# Они будут вызваны Alembic при необходимости 