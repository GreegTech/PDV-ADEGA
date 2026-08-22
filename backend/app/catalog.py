import csv
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CatalogProduct


GTIN_LENGTHS = {8, 12, 13, 14}


def normalize_gtin(value: str) -> str:
    code = re.sub(r"\D", "", value or "")
    if len(code) not in GTIN_LENGTHS:
        return ""
    digits = [int(char) for char in code]
    total = 0
    weight = 3
    for digit in reversed(digits[:-1]):
        total += digit * weight
        weight = 1 if weight == 3 else 3
    check_digit = (10 - total % 10) % 10
    return code if check_digit == digits[-1] else ""


def sync_catalog(db: Session, csv_path: Path) -> dict[str, int]:
    if not csv_path.exists():
        return {"read": 0, "created": 0, "updated": 0}

    existing = {
        item.barcode: item
        for item in db.scalars(select(CatalogProduct)).all()
    }
    read = created = updated = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            code = normalize_gtin(row.get("codigo_barras", ""))
            if not code or row.get("tipo", "PRODUTO").upper() != "PRODUTO":
                continue
            read += 1
            values = {
                "name": (row.get("nome") or "").strip(),
                "brand": (row.get("marca") or "").strip() or None,
                "category": (row.get("categoria") or "Outros").strip(),
                "package_content": (row.get("conteudo_embalagem") or "").strip() or None,
                "unit": (row.get("unidade") or "UN").strip(),
                "source": (row.get("fonte") or "").strip() or None,
            }
            if not values["name"]:
                continue
            item = existing.get(code)
            if item is None:
                item = CatalogProduct(barcode=code, **values)
                db.add(item)
                existing[code] = item
                created += 1
                continue
            changed = False
            for field, value in values.items():
                if getattr(item, field) != value:
                    setattr(item, field, value)
                    changed = True
            updated += int(changed)

    db.commit()
    return {"read": read, "created": created, "updated": updated}
