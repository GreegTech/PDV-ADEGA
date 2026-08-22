from decimal import Decimal
from defusedxml import ElementTree as ET
from .catalog import normalize_gtin

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
MAX_XML_BYTES = 5 * 1024 * 1024

def _text(node, path, default=None):
    el = node.find(path, NS)
    return el.text.strip() if el is not None and el.text else default

def digits(value):
    return "".join(c for c in (value or "") if c.isdigit())

def parse_nfe_xml(raw: bytes):
    if not raw or len(raw) > MAX_XML_BYTES:
        raise ValueError("XML vazio ou acima do limite de 5 MB")
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        raise ValueError("XML inválido") from exc
    inf = root.find(".//nfe:infNFe", NS)
    if inf is None:
        raise ValueError("Documento não contém uma NF-e autorizável")
    ide = inf.find("nfe:ide", NS)
    emit = inf.find("nfe:emit", NS)
    total = inf.find("nfe:total/nfe:ICMSTot", NS)
    access_key = (inf.attrib.get("Id") or "").removeprefix("NFe")
    if len(access_key) != 44 or not access_key.isdigit():
        raise ValueError("Chave de acesso da NF-e inválida")
    items = []
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        if prod is None:
            continue
        raw_gtin = _text(prod, "nfe:cEAN") or _text(prod, "nfe:cEANTrib")
        gtin = None
        if raw_gtin and raw_gtin.upper() not in {"SEM GTIN", "SEM-GTIN"}:
            gtin = normalize_gtin(raw_gtin)
        qty = Decimal(_text(prod, "nfe:qCom", "0"))
        unit_cost = Decimal(_text(prod, "nfe:vUnCom", "0"))
        items.append({
            "line": int(det.attrib.get("nItem", len(items) + 1)),
            "code": _text(prod, "nfe:cProd"),
            "gtin": gtin,
            "description": _text(prod, "nfe:xProd", "Produto"),
            "ncm": _text(prod, "nfe:NCM"),
            "cfop": _text(prod, "nfe:CFOP"),
            "unit": _text(prod, "nfe:uCom", "UN"),
            "quantity": float(qty),
            "unit_cost": float(unit_cost),
            "total": float(Decimal(_text(prod, "nfe:vProd", "0"))),
        })
    return {
        "access_key": access_key,
        "number": _text(ide, "nfe:nNF") if ide is not None else None,
        "series": _text(ide, "nfe:serie") if ide is not None else None,
        "issued_at": (_text(ide, "nfe:dhEmi") or _text(ide, "nfe:dEmi")) if ide is not None else None,
        "supplier": {
            "name": _text(emit, "nfe:xNome") if emit is not None else None,
            "trade_name": _text(emit, "nfe:xFant") if emit is not None else None,
            "document": digits((_text(emit, "nfe:CNPJ") or _text(emit, "nfe:CPF")) if emit is not None else None),
        },
        "invoice_total": float(Decimal(_text(total, "nfe:vNF", "0"))) if total is not None else 0,
        "items": items,
    }
