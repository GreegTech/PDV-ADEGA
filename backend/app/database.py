import os
import re
import unicodedata
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:80] or "adega-torres"

def migrate_existing_schema():
    inspector = inspect(engine)
    statements = []
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "full_name" not in user_columns: statements.append("ALTER TABLE users ADD COLUMN full_name VARCHAR(180)")
    if "email" not in user_columns: statements.append("ALTER TABLE users ADD COLUMN email VARCHAR(180)")
    if "is_platform_admin" not in user_columns: statements.append("ALTER TABLE users ADD COLUMN is_platform_admin BOOLEAN DEFAULT FALSE NOT NULL")

    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "brand" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN brand VARCHAR(120)")
    if "package_content" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN package_content VARCHAR(60)")
    if "unit" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN unit VARCHAR(20) DEFAULT 'UN' NOT NULL")
    if "active" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN active BOOLEAN DEFAULT TRUE NOT NULL")
    if "company_id" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN company_id INTEGER REFERENCES companies(id)")
    if "store_id" not in product_columns: statements.append("ALTER TABLE products ADD COLUMN store_id INTEGER REFERENCES stores(id)")

    supplier_columns = {column["name"] for column in inspector.get_columns("suppliers")}
    if "company_id" not in supplier_columns: statements.append("ALTER TABLE suppliers ADD COLUMN company_id INTEGER REFERENCES companies(id)")

    purchase_columns = {column["name"] for column in inspector.get_columns("purchases")}
    if "company_id" not in purchase_columns: statements.append("ALTER TABLE purchases ADD COLUMN company_id INTEGER REFERENCES companies(id)")
    if "store_id" not in purchase_columns: statements.append("ALTER TABLE purchases ADD COLUMN store_id INTEGER REFERENCES stores(id)")

    sale_columns = {column["name"] for column in inspector.get_columns("sales")}
    if "company_id" not in sale_columns: statements.append("ALTER TABLE sales ADD COLUMN company_id INTEGER REFERENCES companies(id)")
    if "store_id" not in sale_columns: statements.append("ALTER TABLE sales ADD COLUMN store_id INTEGER REFERENCES stores(id)")
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

    movement_columns = {column["name"] for column in inspect(engine).get_columns("stock_movements")}
    movement_statements = []
    if "company_id" not in movement_columns: movement_statements.append("ALTER TABLE stock_movements ADD COLUMN company_id INTEGER REFERENCES companies(id)")
    if "store_id" not in movement_columns: movement_statements.append("ALTER TABLE stock_movements ADD COLUMN store_id INTEGER REFERENCES stores(id)")
    if movement_statements:
        with engine.begin() as connection:
            for statement in movement_statements: connection.execute(text(statement))

    # Converte o banco single-tenant existente em Adega Torres / Loja Principal.
    # As colunas são adicionadas primeiro como opcionais, preenchidas e só então
    # passam a ser obrigatórias, evitando perda ou recriação de tabelas.
    if engine.dialect.name == "postgresql":
        default_name = os.getenv("DEFAULT_COMPANY_NAME", "Adega Torres")
        default_slug = _slug(os.getenv("DEFAULT_COMPANY_SLUG", "adega-torres"))
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO companies (name, slug, active, created_at) VALUES (:name, :slug, TRUE, CURRENT_TIMESTAMP) ON CONFLICT (slug) DO NOTHING"),
                {"name": default_name, "slug": default_slug},
            )
            company_id = connection.execute(text("SELECT id FROM companies WHERE slug=:slug"), {"slug": default_slug}).scalar_one()
            connection.execute(
                text("INSERT INTO stores (company_id, name, code, active, created_at) SELECT :company_id, 'Loja Principal', 'MATRIZ', TRUE, CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM stores WHERE company_id=:company_id)"),
                {"company_id": company_id},
            )
            store_id = connection.execute(text("SELECT id FROM stores WHERE company_id=:company_id ORDER BY id LIMIT 1"), {"company_id": company_id}).scalar_one()
            for table_name in ("products", "purchases", "sales", "stock_movements"):
                connection.execute(text(f"UPDATE {table_name} SET company_id=:company_id WHERE company_id IS NULL"), {"company_id": company_id})
                connection.execute(text(f"UPDATE {table_name} SET store_id=:store_id WHERE store_id IS NULL"), {"store_id": store_id})
                connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN company_id SET NOT NULL"))
                connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN store_id SET NOT NULL"))
            connection.execute(text("UPDATE suppliers SET company_id=:company_id WHERE company_id IS NULL"), {"company_id": company_id})
            connection.execute(text("ALTER TABLE suppliers ALTER COLUMN company_id SET NOT NULL"))

            # Unicidade deixa de ser global: o mesmo GTIN/CNPJ pode existir em tenants diferentes.
            connection.execute(text("ALTER TABLE products DROP CONSTRAINT IF EXISTS products_barcode_key"))
            connection.execute(text("DROP INDEX IF EXISTS ix_products_barcode"))
            connection.execute(text("ALTER TABLE suppliers DROP CONSTRAINT IF EXISTS suppliers_document_key"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_store_barcode ON products (store_id, barcode) WHERE barcode IS NOT NULL"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_suppliers_company_document ON suppliers (company_id, document) WHERE document IS NOT NULL"))
            for table_name, columns in {
                "products": ("company_id", "store_id"),
                "suppliers": ("company_id",),
                "purchases": ("company_id", "store_id"),
                "sales": ("company_id", "store_id"),
                "stock_movements": ("company_id", "store_id"),
            }.items():
                for column in columns:
                    connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_{column} ON {table_name} ({column})"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
