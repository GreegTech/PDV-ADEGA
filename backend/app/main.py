import os
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import Base, engine, SessionLocal, get_db
from .models import User, Product, Sale, SaleItem, StockMovement
from .schemas import Login, ProductCreate, ProductOut, SaleCreate, StockAdjust
from .auth import hash_password, verify_password, make_token, current_user

app = FastAPI(title="Adega Torres API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        username = os.getenv("ADMIN_USER","admin")
        if not db.scalar(select(User).where(User.username == username)):
            pwd = os.environ["ADMIN_PASSWORD"]
            db.add(User(username=username, password_hash=hash_password(pwd), role="admin"))
            db.commit()
    finally:
        db.close()

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/auth/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Usuário ou senha inválidos")
    return {"access_token": make_token(user), "token_type":"bearer", "user":{"id":user.id,"username":user.username,"role":user.role}}

@app.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(Product).order_by(Product.name)).all()

@app.post("/products", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = Product(**data.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    if p.stock:
        db.add(StockMovement(product_id=p.id,type="ENTRADA_INICIAL",quantity=p.stock,user_id=user.id))
        db.commit()
    return p

@app.post("/stock/adjust")
def stock_adjust(data: StockAdjust, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Product, data.product_id)
    if not p: raise HTTPException(404, "Produto não encontrado")
    if p.stock + data.quantity < 0: raise HTTPException(400, "Estoque insuficiente")
    p.stock += data.quantity
    db.add(StockMovement(product_id=p.id,type=data.type,quantity=data.quantity,reference=data.reference,user_id=user.id))
    db.commit()
    return {"ok":True,"stock":p.stock}

@app.post("/sales")
def create_sale(data: SaleCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not data.items: raise HTTPException(400, "Venda sem itens")
    total = Decimal("0")
    prepared = []
    for line in data.items:
        p = db.get(Product, line.product_id)
        if not p: raise HTTPException(404, f"Produto {line.product_id} não encontrado")
        if p.stock < line.quantity: raise HTTPException(400, f"Estoque insuficiente: {p.name}")
        total += Decimal(p.price) * line.quantity
        prepared.append((p,line))
    sale = Sale(total=total,payment_method=data.payment_method,user_id=user.id)
    db.add(sale); db.flush()
    for p,line in prepared:
        p.stock -= line.quantity
        db.add(SaleItem(sale_id=sale.id,product_id=p.id,quantity=line.quantity,unit_price=p.price,unit_cost=p.cost))
        db.add(StockMovement(product_id=p.id,type="VENDA",quantity=-line.quantity,reference=f"VENDA:{sale.id}",user_id=user.id))
    db.commit()
    return {"id":sale.id,"total":float(total),"payment_method":sale.payment_method}

@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    product_count = db.scalar(select(func.count(Product.id))) or 0
    units = db.scalar(select(func.coalesce(func.sum(Product.stock),0))) or 0
    low = db.scalar(select(func.count(Product.id)).where(Product.stock <= Product.min_stock)) or 0
    sales_total = db.scalar(select(func.coalesce(func.sum(Sale.total),0))) or 0
    return {"products":product_count,"stock_units":int(units),"low_stock":low,"sales_total":float(sales_total)}
