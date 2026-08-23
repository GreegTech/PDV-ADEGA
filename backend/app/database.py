import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def migrate_existing_schema():
    inspector = inspect(engine)
    statements = []
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "brand" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN brand VARCHAR(120)")
    if "package_content" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN package_content VARCHAR(60)")
    if "unit" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN unit VARCHAR(20) DEFAULT 'UN' NOT NULL")

    sale_columns = {column["name"] for column in inspector.get_columns("sales")}
    for name in ("gross_total", "discount_total", "cmv_total", "gross_margin"):
        if name not in sale_columns: statements.append(f"ALTER TABLE sales ADD COLUMN {name} NUMERIC(14,2) DEFAULT 0 NOT NULL")

    item_columns = {column["name"] for column in inspector.get_columns("sale_items")}
    for name, sqltype in (
        ("list_unit_price", "NUMERIC(12,2)"), ("discount_unit", "NUMERIC(12,2)"),
        ("effective_unit_price", "NUMERIC(12,2)"), ("gross_total", "NUMERIC(14,2)"),
        ("discount_total", "NUMERIC(14,2)"), ("net_total", "NUMERIC(14,2)"),
        ("cmv_total", "NUMERIC(14,2)")):
        if name not in item_columns: statements.append(f"ALTER TABLE sale_items ADD COLUMN {name} {sqltype} DEFAULT 0 NOT NULL")
    if statements:
        with engine.begin() as connection:
            for statement in statements: connection.execute(text(statement))
        # Vendas antigas preservam o melhor snapshot disponível no esquema anterior.
        with engine.begin() as connection:
            connection.execute(text("UPDATE sale_items SET list_unit_price=unit_price, effective_unit_price=unit_price, gross_total=unit_price*quantity, net_total=unit_price*quantity, cmv_total=unit_cost*quantity WHERE list_unit_price=0 AND unit_price IS NOT NULL"))
            connection.execute(text("UPDATE sales s SET gross_total=s.total, cmv_total=COALESCE((SELECT SUM(si.cmv_total) FROM sale_items si WHERE si.sale_id=s.id),0), gross_margin=s.total-COALESCE((SELECT SUM(si.cmv_total) FROM sale_items si WHERE si.sale_id=s.id),0) WHERE s.gross_total=0"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
