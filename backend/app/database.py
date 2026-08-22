import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def migrate_existing_schema():
    columns = {column["name"] for column in inspect(engine).get_columns("products")}
    statements = []
    if "brand" not in columns:
        statements.append("ALTER TABLE products ADD COLUMN brand VARCHAR(120)")
    if "package_content" not in columns:
        statements.append("ALTER TABLE products ADD COLUMN package_content VARCHAR(60)")
    if "unit" not in columns:
        statements.append("ALTER TABLE products ADD COLUMN unit VARCHAR(20) DEFAULT 'UN' NOT NULL")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
