import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
from utils import log_database_connection, log_info

load_dotenv()

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
DB_HOST = os.getenv("DB_HOST", "db")
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:5432/{POSTGRES_DB}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_database_connection(logger):
    """Проверка подключения к базе данных"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
            log_database_connection(logger, success=True)
            return True
    except SQLAlchemyError as e:
        log_database_connection(logger, success=False, error=str(e))
        return False
    except Exception as e:
        log_database_connection(logger, success=False, error=f"Неожиданная ошибка: {str(e)}")
        return False

def get_db(logger):
    """Получение сессии базы данных"""
    db = SessionLocal()
    log_info(logger, db)
    try:
        yield db
    finally:
        db.close() 