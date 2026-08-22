import os
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, SessionLocal, get_db, migrate_existing_schema
from .models import User, Product, CatalogProduct, Supplier, Purchase, PurchaseItem, Sale, SaleItem, StockMovement
from .schemas import Login, ProductCreate, ProductOut, CatalogProductOut, SupplierCreate, SupplierOut, PurchaseCreate, SaleCreate, StockAdjust
from .auth import hash_password, verify_password, make_token, current_user
from .catalog import normalize_gtin, sync_catalog

app = FastAPI(title="Adega Torres API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
MONEY = Decimal("0.01")

def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    migrate_existing_schema()
    db = SessionLocal()
    try:
        username = os.getenv("ADMIN_USER","admin")
        if not db.scalar(select(User).where(User.username == username)):
            pwd = os.environ["ADMIN_PASSWORD"]
            db.add(User(username=username, password_hash=hash_password(pwd), role="admin")); db.commit()
        default_catalog = Path(__file__).resolve().parent.parent / "data" / "catalogo_produtos_adega_torres.csv"
        sync_catalog(db, Path(os.getenv("CATALOG_CSV_PATH", default_catalog)))
    finally: db.close()

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/auth/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Usuário ou senha inválidos")
    return {"access_token":make_token(user),"token_type":"bearer","user":{"id":user.id,"username":user.username,"role":user.role}}

@app.get("/products", response_model=list[ProductOut])
def products(db: Session=Depends(get_db), user: User=Depends(current_user)): return db.scalars(select(Product).order_by(Product.name)).all()

@app.post("/products", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session=Depends(get_db), user: User=Depends(current_user)):
    barcode=data.barcode.strip() if data.barcode else None
    if barcode and db.scalar(select(Product).where(Product.barcode==barcode)): raise HTTPException(409,"Código de barras já cadastrado")
    p=Product(**data.model_dump(exclude={"barcode"}),barcode=barcode)
    try:
        db.add(p); db.flush()
        if p.stock: db.add(StockMovement(product_id=p.id,type="ENTRADA_INICIAL",quantity=p.stock,reference=f"CUSTO:{money(p.cost)}",user_id=user.id))
        db.commit(); db.refresh(p)
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"Código de barras já cadastrado")
    return p

@app.get("/catalog/barcode/{barcode}")
def catalog_by_barcode(barcode:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    code=normalize_gtin(barcode)
    if not code: raise HTTPException(400,"GTIN/EAN inválido")
    registered=db.scalar(select(Product).where(Product.barcode==code))
    if registered:return {"status":"registered","product":ProductOut.model_validate(registered)}
    suggestion=db.scalar(select(CatalogProduct).where(CatalogProduct.barcode==code))
    if suggestion:return {"status":"catalog","suggestion":CatalogProductOut.model_validate(suggestion)}
    return {"status":"not_found","barcode":code}

@app.get("/suppliers", response_model=list[SupplierOut])
def suppliers(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return db.scalars(select(Supplier).where(Supplier.active==True).order_by(Supplier.name)).all()

@app.post("/suppliers", response_model=SupplierOut)
def create_supplier(data:SupplierCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    supplier=Supplier(**data.model_dump())
    try:
        db.add(supplier); db.commit(); db.refresh(supplier); return supplier
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"Fornecedor/documento já cadastrado")

@app.post("/purchases")
def create_purchase(data:PurchaseCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not data.items: raise HTTPException(400,"Compra sem itens")
    supplier=db.get(Supplier,data.supplier_id)
    if not supplier or not supplier.active: raise HTTPException(404,"Fornecedor não encontrado")
    purchase=Purchase(supplier_id=supplier.id,document=data.document,user_id=user.id,total=0)
    db.add(purchase); db.flush(); total=Decimal("0")
    try:
        for line in data.items:
            product=db.execute(select(Product).where(Product.id==line.product_id).with_for_update()).scalar_one_or_none()
            if not product: raise HTTPException(404,f"Produto {line.product_id} não encontrado")
            qty=line.quantity; incoming=money(line.unit_cost); old_stock=product.stock; old_avg=money(product.cost)
            old_value=old_avg*old_stock; incoming_value=incoming*qty; new_stock=old_stock+qty
            new_avg=money((old_value+incoming_value)/new_stock)
            line_total=money(incoming*qty); total+=line_total
            db.add(PurchaseItem(purchase_id=purchase.id,product_id=product.id,quantity=qty,unit_cost=incoming,total_cost=line_total,previous_stock=old_stock,previous_avg_cost=old_avg,new_stock=new_stock,new_avg_cost=new_avg))
            product.stock=new_stock; product.cost=new_avg
            db.add(StockMovement(product_id=product.id,type="COMPRA",quantity=qty,reference=f"COMPRA:{purchase.id};CUSTO:{incoming};CMP:{old_avg}->{new_avg}",user_id=user.id))
        purchase.total=money(total); db.commit(); db.refresh(purchase)
    except Exception:
        db.rollback(); raise
    return {"id":purchase.id,"supplier_id":supplier.id,"supplier":supplier.name,"document":purchase.document,"total":float(purchase.total),"items":len(data.items)}

@app.get("/purchases")
def purchases(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.execute(select(Purchase,Supplier.name).join(Supplier,Supplier.id==Purchase.supplier_id).order_by(Purchase.created_at.desc()).limit(100)).all()
    return [{"id":p.id,"supplier_id":p.supplier_id,"supplier":name,"document":p.document,"total":float(p.total),"created_at":p.created_at} for p,name in rows]

@app.post("/stock/adjust")
def stock_adjust(data:StockAdjust,db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=db.get(Product,data.product_id)
    if not p: raise HTTPException(404,"Produto não encontrado")
    if p.stock+data.quantity<0: raise HTTPException(400,"Estoque insuficiente")
    # Ajustes físicos não alteram o CMP. Entrada comercial deve ser registrada em /purchases.
    p.stock+=data.quantity; db.add(StockMovement(product_id=p.id,type=data.type,quantity=data.quantity,reference=data.reference,user_id=user.id)); db.commit()
    return {"ok":True,"stock":p.stock,"average_cost":float(p.cost)}

@app.post("/sales")
def create_sale(data:SaleCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not data.items: raise HTTPException(400,"Venda sem itens")
    total=Decimal("0"); prepared=[]
    for line in data.items:
        p=db.get(Product,line.product_id)
        if not p: raise HTTPException(404,f"Produto {line.product_id} não encontrado")
        if p.stock<line.quantity: raise HTTPException(400,f"Estoque insuficiente: {p.name}")
        total+=Decimal(p.price)*line.quantity; prepared.append((p,line))
    sale=Sale(total=total,payment_method=data.payment_method,user_id=user.id); db.add(sale); db.flush()
    for p,line in prepared:
        p.stock-=line.quantity; db.add(SaleItem(sale_id=sale.id,product_id=p.id,quantity=line.quantity,unit_price=p.price,unit_cost=p.cost)); db.add(StockMovement(product_id=p.id,type="VENDA",quantity=-line.quantity,reference=f"VENDA:{sale.id}",user_id=user.id))
    db.commit(); return {"id":sale.id,"total":float(total),"payment_method":sale.payment_method}

@app.get("/dashboard")
def dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
    product_count=db.scalar(select(func.count(Product.id))) or 0; units=db.scalar(select(func.coalesce(func.sum(Product.stock),0))) or 0; low=db.scalar(select(func.count(Product.id)).where(Product.stock<=Product.min_stock)) or 0; sales_total=db.scalar(select(func.coalesce(func.sum(Sale.total),0))) or 0
    return {"products":product_count,"stock_units":int(units),"low_stock":low,"sales_total":float(sales_total)}
