import os
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, SessionLocal, get_db, migrate_existing_schema
from .models import User, Product, CatalogProduct, Supplier, Purchase, PurchaseItem, Sale, SaleItem, StockMovement
from .schemas import Login, ProductCreate, ProductOut, CatalogProductOut, SupplierCreate, SupplierOut, PurchaseCreate, SaleCreate, StockAdjust
from .auth import hash_password, verify_password, make_token, current_user
from .catalog import normalize_gtin, sync_catalog
from .nfe import parse_nfe_xml, MAX_XML_BYTES

app=FastAPI(title="Adega Torres API",version="0.5.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
MONEY=Decimal("0.01")
def money(value): return Decimal(str(value)).quantize(MONEY,rounding=ROUND_HALF_UP)
@app.on_event("startup")
def startup():
 Base.metadata.create_all(engine);migrate_existing_schema();db=SessionLocal()
 try:
  username=os.getenv("ADMIN_USER","admin")
  if not db.scalar(select(User).where(User.username==username)):db.add(User(username=username,password_hash=hash_password(os.environ["ADMIN_PASSWORD"]),role="admin"));db.commit()
  sync_catalog(db,Path(os.getenv("CATALOG_CSV_PATH",Path(__file__).resolve().parent.parent/"data"/"catalogo_produtos_adega_torres.csv")))
 finally:db.close()
@app.get("/health")
def health():return {"status":"ok"}
@app.post("/auth/login")
def login(data:Login,db:Session=Depends(get_db)):
 user=db.scalar(select(User).where(User.username==data.username))
 if not user or not verify_password(data.password,user.password_hash):raise HTTPException(401,"Usuário ou senha inválidos")
 return {"access_token":make_token(user),"token_type":"bearer","user":{"id":user.id,"username":user.username,"role":user.role}}
@app.get("/products",response_model=list[ProductOut])
def products(db:Session=Depends(get_db),user:User=Depends(current_user)):return db.scalars(select(Product).order_by(Product.name)).all()
@app.post("/products",response_model=ProductOut)
def create_product(data:ProductCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
 barcode=data.barcode.strip() if data.barcode else None
 if barcode and db.scalar(select(Product).where(Product.barcode==barcode)):raise HTTPException(409,"Código de barras já cadastrado")
 p=Product(**data.model_dump(exclude={"barcode"}),barcode=barcode)
 try:
  db.add(p);db.flush()
  if p.stock:db.add(StockMovement(product_id=p.id,type="ENTRADA_INICIAL",quantity=p.stock,reference=f"CUSTO:{money(p.cost)}",user_id=user.id))
  db.commit();db.refresh(p)
 except IntegrityError:db.rollback();raise HTTPException(409,"Código de barras já cadastrado")
 return p
@app.get("/catalog/barcode/{barcode}")
def catalog_by_barcode(barcode:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
 code=normalize_gtin(barcode)
 if not code:raise HTTPException(400,"GTIN/EAN inválido")
 registered=db.scalar(select(Product).where(Product.barcode==code))
 if registered:return {"status":"registered","product":ProductOut.model_validate(registered)}
 suggestion=db.scalar(select(CatalogProduct).where(CatalogProduct.barcode==code))
 if suggestion:return {"status":"catalog","suggestion":CatalogProductOut.model_validate(suggestion)}
 return {"status":"not_found","barcode":code}
@app.get("/suppliers",response_model=list[SupplierOut])
def suppliers(db:Session=Depends(get_db),user:User=Depends(current_user)):return db.scalars(select(Supplier).where(Supplier.active==True).order_by(Supplier.name)).all()
@app.post("/suppliers",response_model=SupplierOut)
def create_supplier(data:SupplierCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
 supplier=Supplier(**data.model_dump())
 try:db.add(supplier);db.commit();db.refresh(supplier);return supplier
 except IntegrityError:db.rollback();raise HTTPException(409,"Fornecedor/documento já cadastrado")
@app.post("/nfe/xml/preview")
async def nfe_xml_preview(file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
 if file.content_type not in {"application/xml","text/xml","application/octet-stream"} and not (file.filename or "").lower().endswith(".xml"):raise HTTPException(400,"Envie um arquivo XML de NF-e")
 raw=await file.read(MAX_XML_BYTES+1)
 try:data=parse_nfe_xml(raw)
 except ValueError as exc:raise HTTPException(400,str(exc))
 existing=db.scalar(select(Purchase).where(Purchase.document==data["access_key"]));supplier=None
 if data["supplier"]["document"]:supplier=db.scalar(select(Supplier).where(Supplier.document==data["supplier"]["document"]))
 for item in data["items"]:
  product=catalog=None
  if item["gtin"]:
   product=db.scalar(select(Product).where(Product.barcode==item["gtin"]))
   if not product:catalog=db.scalar(select(CatalogProduct).where(CatalogProduct.barcode==item["gtin"]))
  if product:item["match"]={"status":"registered","product_id":product.id,"product_name":product.name}
  elif catalog:item["match"]={"status":"catalog","name":catalog.name,"brand":catalog.brand,"category":catalog.category,"package_content":catalog.package_content,"unit":catalog.unit}
  else:item["match"]={"status":"not_found"}
 data["supplier_match"]={"id":supplier.id,"name":supplier.name} if supplier else None;data["already_imported"]=bool(existing);return data
@app.post("/purchases")
def create_purchase(data:PurchaseCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
 if not data.items:raise HTTPException(400,"Compra sem itens")
 supplier=db.get(Supplier,data.supplier_id)
 if not supplier or not supplier.active:raise HTTPException(404,"Fornecedor não encontrado")
 if data.document and db.scalar(select(Purchase).where(Purchase.document==data.document)):raise HTTPException(409,"Documento/NF-e já registrado")
 purchase=Purchase(supplier_id=supplier.id,document=data.document,user_id=user.id,total=0);db.add(purchase);db.flush();total=Decimal("0")
 try:
  for line in data.items:
   product=db.execute(select(Product).where(Product.id==line.product_id).with_for_update()).scalar_one_or_none()
   if not product:raise HTTPException(404,f"Produto {line.product_id} não encontrado")
   qty=line.quantity;incoming=money(line.unit_cost);old_stock=product.stock;old_avg=money(product.cost);new_stock=old_stock+qty;new_avg=money(((old_avg*old_stock)+(incoming*qty))/new_stock);line_total=money(incoming*qty);total+=line_total
   db.add(PurchaseItem(purchase_id=purchase.id,product_id=product.id,quantity=qty,unit_cost=incoming,total_cost=line_total,previous_stock=old_stock,previous_avg_cost=old_avg,new_stock=new_stock,new_avg_cost=new_avg));product.stock=new_stock;product.cost=new_avg;db.add(StockMovement(product_id=product.id,type="COMPRA",quantity=qty,reference=f"COMPRA:{purchase.id};CUSTO:{incoming};CMP:{old_avg}->{new_avg}",user_id=user.id))
  purchase.total=money(total);db.commit();db.refresh(purchase)
 except Exception:db.rollback();raise
 return {"id":purchase.id,"supplier_id":supplier.id,"supplier":supplier.name,"document":purchase.document,"total":float(purchase.total),"items":len(data.items)}
@app.get("/purchases")
def purchases(db:Session=Depends(get_db),user:User=Depends(current_user)):
 rows=db.execute(select(Purchase,Supplier.name).join(Supplier,Supplier.id==Purchase.supplier_id).order_by(Purchase.created_at.desc()).limit(100)).all();return [{"id":p.id,"supplier_id":p.supplier_id,"supplier":name,"document":p.document,"total":float(p.total),"created_at":p.created_at} for p,name in rows]
@app.get("/purchases/{purchase_id}")
def purchase_detail(purchase_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
 row=db.execute(select(Purchase,Supplier.name).join(Supplier,Supplier.id==Purchase.supplier_id).where(Purchase.id==purchase_id)).first()
 if not row:raise HTTPException(404,"Compra não encontrada")
 purchase,supplier_name=row;items=db.execute(select(PurchaseItem,Product.name,Product.barcode).join(Product,Product.id==PurchaseItem.product_id).where(PurchaseItem.purchase_id==purchase_id).order_by(PurchaseItem.id)).all();return {"id":purchase.id,"supplier_id":purchase.supplier_id,"supplier":supplier_name,"document":purchase.document,"total":float(purchase.total),"created_at":purchase.created_at,"items":[{"product_id":i.product_id,"product":name,"barcode":barcode,"quantity":i.quantity,"unit_cost":float(i.unit_cost),"total_cost":float(i.total_cost),"previous_stock":i.previous_stock,"previous_avg_cost":float(i.previous_avg_cost),"new_stock":i.new_stock,"new_avg_cost":float(i.new_avg_cost)} for i,name,barcode in items]}
@app.post("/stock/adjust")
def stock_adjust(data:StockAdjust,db:Session=Depends(get_db),user:User=Depends(current_user)):
 p=db.get(Product,data.product_id)
 if not p:raise HTTPException(404,"Produto não encontrado")
 if p.stock+data.quantity<0:raise HTTPException(400,"Estoque insuficiente")
 p.stock+=data.quantity;db.add(StockMovement(product_id=p.id,type=data.type,quantity=data.quantity,reference=data.reference,user_id=user.id));db.commit();return {"ok":True,"stock":p.stock,"average_cost":float(p.cost)}
@app.post("/sales")
def create_sale(data:SaleCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
 if not data.items:raise HTTPException(400,"Venda sem itens")
 gross=discounts=net=cmv=Decimal("0");prepared=[]
 try:
  for line in data.items:
   p=db.execute(select(Product).where(Product.id==line.product_id).with_for_update()).scalar_one_or_none()
   if not p:raise HTTPException(404,f"Produto {line.product_id} não encontrado")
   if p.stock<line.quantity:raise HTTPException(400,f"Estoque insuficiente: {p.name}")
   list_price=money(p.price);discount=money(line.discount_unit);cost=money(p.cost)
   if discount>list_price:raise HTTPException(400,f"Desconto maior que o preço de tabela: {p.name}")
   effective=money(list_price-discount);line_gross=money(list_price*line.quantity);line_discount=money(discount*line.quantity);line_net=money(effective*line.quantity);line_cmv=money(cost*line.quantity)
   gross+=line_gross;discounts+=line_discount;net+=line_net;cmv+=line_cmv;prepared.append((p,line,list_price,discount,effective,cost,line_gross,line_discount,line_net,line_cmv))
  sale=Sale(total=money(net),gross_total=money(gross),discount_total=money(discounts),cmv_total=money(cmv),gross_margin=money(net-cmv),payment_method=data.payment_method,user_id=user.id);db.add(sale);db.flush()
  for p,line,list_price,discount,effective,cost,line_gross,line_discount,line_net,line_cmv in prepared:
   p.stock-=line.quantity
   db.add(SaleItem(sale_id=sale.id,product_id=p.id,quantity=line.quantity,list_unit_price=list_price,discount_unit=discount,effective_unit_price=effective,unit_cost=cost,gross_total=line_gross,discount_total=line_discount,net_total=line_net,cmv_total=line_cmv,unit_price=effective))
   db.add(StockMovement(product_id=p.id,type="VENDA",quantity=-line.quantity,reference=f"VENDA:{sale.id}",user_id=user.id))
  db.commit();db.refresh(sale)
 except Exception:db.rollback();raise
 margin_pct=(money((sale.gross_margin/sale.total)*100) if sale.total else Decimal("0"))
 return {"id":sale.id,"gross_total":float(sale.gross_total),"discount_total":float(sale.discount_total),"total":float(sale.total),"cmv_total":float(sale.cmv_total),"gross_margin":float(sale.gross_margin),"gross_margin_percent":float(margin_pct),"payment_method":sale.payment_method}
@app.get("/sales/{sale_id}")
def sale_detail(sale_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
 sale=db.get(Sale,sale_id)
 if not sale:raise HTTPException(404,"Venda não encontrada")
 rows=db.execute(select(SaleItem,Product.name,Product.barcode).join(Product,Product.id==SaleItem.product_id).where(SaleItem.sale_id==sale_id).order_by(SaleItem.id)).all()
 return {"id":sale.id,"created_at":sale.created_at,"payment_method":sale.payment_method,"gross_total":float(sale.gross_total),"discount_total":float(sale.discount_total),"total":float(sale.total),"cmv_total":float(sale.cmv_total),"gross_margin":float(sale.gross_margin),"items":[{"product_id":i.product_id,"product":name,"barcode":barcode,"quantity":i.quantity,"list_unit_price":float(i.list_unit_price),"discount_unit":float(i.discount_unit),"effective_unit_price":float(i.effective_unit_price),"unit_cost":float(i.unit_cost),"gross_total":float(i.gross_total),"discount_total":float(i.discount_total),"net_total":float(i.net_total),"cmv_total":float(i.cmv_total),"gross_margin":float(i.net_total-i.cmv_total)} for i,name,barcode in rows]}
@app.get("/dashboard")
def dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
 return {"products":db.scalar(select(func.count(Product.id))) or 0,"stock_units":int(db.scalar(select(func.coalesce(func.sum(Product.stock),0))) or 0),"low_stock":db.scalar(select(func.count(Product.id)).where(Product.stock<=Product.min_stock)) or 0,"sales_total":float(db.scalar(select(func.coalesce(func.sum(Sale.total),0))) or 0),"discount_total":float(db.scalar(select(func.coalesce(func.sum(Sale.discount_total),0))) or 0),"cmv_total":float(db.scalar(select(func.coalesce(func.sum(Sale.cmv_total),0))) or 0),"gross_margin":float(db.scalar(select(func.coalesce(func.sum(Sale.gross_margin),0))) or 0)}
