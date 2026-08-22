import csv
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.catalog import normalize_gtin, sync_catalog
from app.database import Base
from app.models import CatalogProduct


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def test_normalize_gtin_validates_length_and_check_digit(self):
        self.assertEqual(normalize_gtin("7894900010015"), "7894900010015")
        self.assertEqual(normalize_gtin("082184090442"), "082184090442")
        self.assertEqual(normalize_gtin("7894900010016"), "")
        self.assertEqual(normalize_gtin("COMBO-001"), "")

    def test_sync_catalog_imports_products_and_skips_combos(self):
        headers = ["codigo_barras", "nome", "marca", "categoria", "conteudo_embalagem", "unidade", "tipo", "fonte"]
        rows = [
            ["7894900010015", "Coca-Cola lata 350 ML", "Coca-Cola", "Refrigerantes", "350 ML", "UN", "PRODUTO", "https://example.test/product"],
            ["", "Combo teste", "Adega Torres", "Combos", "", "UN", "COMBO", "interno"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "catalog.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                writer.writerows(rows)
            with Session(self.engine) as db:
                result = sync_catalog(db, csv_path)
                self.assertEqual(result, {"read": 1, "created": 1, "updated": 0})
                self.assertEqual(db.scalar(select(func.count(CatalogProduct.id))), 1)
                product = db.scalar(select(CatalogProduct))
                self.assertEqual(product.brand, "Coca-Cola")

                second = sync_catalog(db, csv_path)
                self.assertEqual(second, {"read": 1, "created": 0, "updated": 0})


if __name__ == "__main__":
    unittest.main()
