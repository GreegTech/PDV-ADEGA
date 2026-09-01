import os
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_context, hash_password, make_token
from .database import get_db
from .models import (
    Company,
    CashRegister,
    Membership,
    MembershipStore,
    Permission,
    Role,
    RolePermission,
    Store,
    User,
)
from .schemas import (
    CompanyCreate,
    CompanyUpdate,
    ContextSwitch,
    MembershipUpdate,
    RoleCreate,
    RoleUpdate,
    StoreCreate,
    StoreUpdate,
    TenantUserCreate,
)

router = APIRouter()

PERMISSIONS = {
    "companies.manage": ("Gerenciar empresa", "admin"),
    "stores.manage": ("Gerenciar lojas", "admin"),
    "users.manage": ("Gerenciar usuários e acessos", "admin"),
    "dashboard.read": ("Consultar painel operacional", "dashboard"),
    "products.read": ("Consultar produtos", "products"),
    "products.write": ("Cadastrar e editar produtos", "products"),
    "inventory.read": ("Consultar estoque", "inventory"),
    "inventory.write": ("Movimentar estoque", "inventory"),
    "inventory.transfer": ("Transferir estoque entre lojas", "inventory"),
    "cash.read": ("Consultar caixa", "cash"),
    "cash.operate": ("Abrir e fechar o próprio caixa", "cash"),
    "cash.adjust": ("Realizar sangria e suprimento", "cash"),
    "sales.create": ("Realizar vendas", "sales"),
    "sales.read": ("Consultar vendas", "sales"),
    "purchases.read": ("Consultar compras", "purchases"),
    "purchases.write": ("Registrar compras e NF-e", "purchases"),
    "reports.read": ("Consultar relatórios", "reports"),
}

ROLE_TEMPLATES = {
    "admin": {
        "name": "Administrador",
        "description": "Controle total da empresa e de todas as lojas.",
        "permissions": set(PERMISSIONS),
    },
    "manager": {
        "name": "Gerente",
        "description": "Opera e acompanha lojas, sem alterar a empresa ou usuários.",
        "permissions": set(PERMISSIONS) - {"companies.manage", "users.manage"},
    },
    "operator": {
        "name": "Operador",
        "description": "Vendas e consultas operacionais da loja autorizada.",
        "permissions": {"dashboard.read", "products.read", "inventory.read", "sales.create", "sales.read", "cash.read", "cash.operate"},
    },
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:80]


def seed_permissions_and_roles(db: Session, company: Company) -> dict[str, Role]:
    permissions: dict[str, Permission] = {}
    for code, (name, module) in PERMISSIONS.items():
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if not permission:
            permission = Permission(code=code, name=name, module=module)
            db.add(permission)
            db.flush()
        permissions[code] = permission

    roles: dict[str, Role] = {}
    for code, template in ROLE_TEMPLATES.items():
        role = db.scalar(select(Role).where(Role.company_id == company.id, Role.code == code))
        if not role:
            role = Role(
                company_id=company.id,
                code=code,
                name=template["name"],
                description=template["description"],
                system=True,
            )
            db.add(role)
            db.flush()
        roles[code] = role
        existing = set(
            db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all()
        )
        for permission_code in template["permissions"]:
            permission = permissions[permission_code]
            if permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.flush()
    return roles


def ensure_default_tenant(db: Session, admin_user: User) -> tuple[Company, Store, Membership]:
    slug = slugify(os.getenv("DEFAULT_COMPANY_SLUG", "adega-torres")) or "adega-torres"
    company = db.scalar(select(Company).where(Company.slug == slug))
    if not company:
        company = Company(name=os.getenv("DEFAULT_COMPANY_NAME", "Adega Torres"), slug=slug)
        db.add(company)
        db.flush()
    store = db.scalar(select(Store).where(Store.company_id == company.id).order_by(Store.id))
    if not store:
        store = Store(company_id=company.id, name="Loja Principal", code="MATRIZ")
        db.add(store)
        db.flush()
    if not db.scalar(select(CashRegister).where(CashRegister.store_id == store.id)):
        db.add(CashRegister(company_id=company.id, store_id=store.id, name="Caixa Principal", code="CAIXA-01"))
        db.flush()
    roles = seed_permissions_and_roles(db, company)
    admin_user.role = "admin"
    admin_user.is_platform_admin = True
    membership = None
    # Todos os usuários do PDV antigo entram no tenant padrão preservando o perfil.
    # Como antes havia só uma loja, operadores e gerentes recebem a Loja Principal.
    for legacy_user in db.scalars(select(User).order_by(User.id)).all():
        role_code = legacy_user.role if legacy_user.role in roles else "operator"
        existing = db.scalar(
            select(Membership).where(Membership.user_id == legacy_user.id, Membership.company_id == company.id)
        )
        if not existing:
            existing = Membership(
                user_id=legacy_user.id,
                company_id=company.id,
                role_id=roles[role_code].id,
                all_stores=role_code == "admin",
            )
            db.add(existing)
            db.flush()
        if role_code != "admin" and not db.scalar(
            select(MembershipStore.id).where(
                MembershipStore.membership_id == existing.id,
                MembershipStore.store_id == store.id,
            )
        ):
            db.add(MembershipStore(membership_id=existing.id, store_id=store.id))
        if legacy_user.id == admin_user.id:
            existing.role_id = roles["admin"].id
            existing.all_stores = True
            existing.active = True
            membership = existing
    if membership is None:
        raise RuntimeError("Administrador padrão não pôde ser vinculado à empresa")
    db.commit()
    return company, store, membership


def role_permissions(db: Session, role_id: int) -> set[str]:
    return set(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        ).all()
    )


def allowed_stores(db: Session, membership: Membership) -> list[Store]:
    query = select(Store).where(Store.company_id == membership.company_id, Store.active == True)
    if not membership.all_stores:
        query = query.join(MembershipStore, MembershipStore.store_id == Store.id).where(
            MembershipStore.membership_id == membership.id
        )
    return db.scalars(query.order_by(Store.name)).all()


def serialize_context(db: Session, membership: Membership, selected_store_id: int | None = None):
    company = db.get(Company, membership.company_id)
    role = db.get(Role, membership.role_id)
    stores = allowed_stores(db, membership)
    return {
        "membership_id": membership.id,
        "company": {"id": company.id, "name": company.name, "slug": company.slug},
        "role": {"id": role.id, "code": role.code, "name": role.name},
        "all_stores": membership.all_stores,
        "stores": [{"id": s.id, "name": s.name, "code": s.code} for s in stores],
        "selected_store_id": selected_store_id,
        "permissions": sorted(role_permissions(db, role.id)),
    }


def require(permission: str):
    def dependency(context=Depends(current_context)):
        if permission not in context.permissions:
            raise HTTPException(403, f"Permissão necessária: {permission}")
        return context

    return dependency


@router.get("/auth/me")
def auth_me(db: Session = Depends(get_db), context=Depends(current_context)):
    return {
        "user": {
            "id": context.id,
            "username": context.username,
            "full_name": context.user.full_name,
            "email": context.user.email,
            "is_platform_admin": context.user.is_platform_admin,
        },
        "context": serialize_context(db, context.membership, context.store_id),
    }


@router.get("/auth/contexts")
def auth_contexts(db: Session = Depends(get_db), context=Depends(current_context)):
    memberships = db.scalars(
        select(Membership)
        .join(Company, Company.id == Membership.company_id)
        .where(Membership.user_id == context.id, Membership.active == True, Company.active == True)
        .order_by(Company.name)
    ).all()
    return [serialize_context(db, membership, context.store_id if membership.id == context.membership.id else None) for membership in memberships]


@router.post("/auth/switch-context")
def switch_context(data: ContextSwitch, db: Session = Depends(get_db), context=Depends(current_context)):
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == context.id,
            Membership.company_id == data.company_id,
            Membership.active == True,
        )
    )
    if not membership:
        raise HTTPException(403, "Usuário não pertence à empresa selecionada")
    store = next((item for item in allowed_stores(db, membership) if item.id == data.store_id), None)
    if not store:
        raise HTTPException(403, "Usuário não possui acesso à loja selecionada")
    role = db.get(Role, membership.role_id)
    return {
        "access_token": make_token(context.user, membership, store),
        "token_type": "bearer",
        "user": {"id": context.id, "username": context.username, "role": role.code},
        "context": serialize_context(db, membership, store.id),
    }


@router.get("/admin/companies")
def list_companies(db: Session = Depends(get_db), context=Depends(current_context)):
    if context.user.is_platform_admin:
        companies = db.scalars(select(Company).order_by(Company.name)).all()
    else:
        companies = db.scalars(
            select(Company)
            .join(Membership, Membership.company_id == Company.id)
            .where(Membership.user_id == context.id, Membership.active == True)
            .order_by(Company.name)
        ).all()
    return [
        {"id": c.id, "name": c.name, "legal_name": c.legal_name, "document": c.document, "slug": c.slug, "active": c.active}
        for c in companies
    ]


@router.post("/admin/companies")
def create_company(data: CompanyCreate, db: Session = Depends(get_db), context=Depends(current_context)):
    if not context.user.is_platform_admin:
        raise HTTPException(403, "Apenas o administrador da plataforma pode criar empresas")
    slug = slugify(data.slug or data.name)
    if not slug:
        raise HTTPException(400, "Slug da empresa inválido")
    company = Company(name=data.name.strip(), legal_name=data.legal_name, document=data.document, slug=slug)
    try:
        db.add(company)
        db.flush()
        store = Store(company_id=company.id, name=data.store_name.strip(), code="MATRIZ", document=data.document)
        db.add(store)
        db.flush()
        db.add(CashRegister(company_id=company.id, store_id=store.id, name="Caixa Principal", code="CAIXA-01"))
        roles = seed_permissions_and_roles(db, company)
        db.add(Membership(user_id=context.id, company_id=company.id, role_id=roles["admin"].id, all_stores=True))
        db.commit()
        return {"id": company.id, "name": company.name, "slug": company.slug, "store_id": store.id}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Empresa, CNPJ/CPF ou identificador já cadastrado")


@router.patch("/admin/company")
def update_company(data: CompanyUpdate, db: Session = Depends(get_db), context=Depends(require("companies.manage"))):
    company = db.get(Company, context.company_id)
    company.name = data.name.strip()
    company.legal_name = data.legal_name
    company.document = data.document
    try:
        db.commit()
        return {"id": company.id, "name": company.name, "legal_name": company.legal_name, "document": company.document, "slug": company.slug, "active": company.active}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "CNPJ/CPF já utilizado por outra empresa")


@router.get("/admin/stores")
def list_stores(db: Session = Depends(get_db), context=Depends(require("stores.manage"))):
    stores = db.scalars(select(Store).where(Store.company_id == context.company_id).order_by(Store.name)).all()
    return [{"id": s.id, "name": s.name, "code": s.code, "document": s.document, "active": s.active} for s in stores]


@router.post("/admin/stores")
def create_store(data: StoreCreate, db: Session = Depends(get_db), context=Depends(require("stores.manage"))):
    store = Store(
        company_id=context.company_id,
        name=data.name.strip(),
        code=data.code.strip().upper(),
        document=data.document,
    )
    try:
        db.add(store)
        db.flush()
        db.add(CashRegister(company_id=context.company_id, store_id=store.id, name="Caixa Principal", code="CAIXA-01"))
        db.commit()
        db.refresh(store)
        return {"id": store.id, "name": store.name, "code": store.code, "document": store.document, "active": store.active}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Código de loja já utilizado nesta empresa")


@router.patch("/admin/stores/{store_id}")
def update_store(store_id: int, data: StoreUpdate, db: Session = Depends(get_db), context=Depends(require("stores.manage"))):
    store = db.scalar(select(Store).where(Store.id == store_id, Store.company_id == context.company_id))
    if not store:
        raise HTTPException(404, "Loja não encontrada")
    if store.id == context.store_id and not data.active:
        raise HTTPException(409, "Não é possível desativar a loja usada na sessão atual")
    store.name = data.name.strip()
    store.code = data.code.strip().upper()
    store.document = data.document
    store.active = data.active
    try:
        db.commit()
        return {"id": store.id, "name": store.name, "code": store.code, "document": store.document, "active": store.active}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Código de loja já utilizado nesta empresa")


@router.get("/admin/roles")
def list_roles(db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    roles = db.scalars(select(Role).where(Role.company_id == context.company_id, Role.active == True).order_by(Role.name)).all()
    return [
        {"id": role.id, "code": role.code, "name": role.name, "description": role.description, "permissions": sorted(role_permissions(db, role.id))}
        for role in roles
    ]


@router.get("/admin/permissions")
def list_permissions(db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    permissions = db.scalars(select(Permission).order_by(Permission.module, Permission.name)).all()
    return [{"code": p.code, "name": p.name, "module": p.module} for p in permissions]


@router.post("/admin/roles")
def create_role(data: RoleCreate, db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    code = slugify(data.code or data.name).replace("-", "_")[:40]
    permissions = db.scalars(select(Permission).where(Permission.code.in_(set(data.permission_codes)))).all()
    if len(permissions) != len(set(data.permission_codes)):
        raise HTTPException(400, "Uma ou mais permissões são inválidas")
    try:
        role = Role(company_id=context.company_id, code=code, name=data.name.strip(), description=data.description, system=False)
        db.add(role)
        db.flush()
        db.add_all([RolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions])
        db.commit()
        return {"id": role.id, "code": role.code, "name": role.name, "permissions": sorted(data.permission_codes)}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe um perfil com esse código nesta empresa")


@router.patch("/admin/roles/{role_id}")
def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    role = db.scalar(select(Role).where(Role.id == role_id, Role.company_id == context.company_id))
    if not role:
        raise HTTPException(404, "Perfil não encontrado")
    if role.system:
        raise HTTPException(409, "Perfis padrão são protegidos; crie um perfil personalizado")
    permissions = db.scalars(select(Permission).where(Permission.code.in_(set(data.permission_codes)))).all()
    if len(permissions) != len(set(data.permission_codes)):
        raise HTTPException(400, "Uma ou mais permissões são inválidas")
    role.name = data.name.strip()
    role.description = data.description
    role.active = data.active
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    db.add_all([RolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions])
    db.commit()
    return {"id": role.id, "code": role.code, "name": role.name, "active": role.active, "permissions": sorted(data.permission_codes)}


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    rows = db.execute(
        select(Membership, User, Role)
        .join(User, User.id == Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.company_id == context.company_id)
        .order_by(User.username)
    ).all()
    result = []
    for membership, user, role in rows:
        store_ids = db.scalars(select(MembershipStore.store_id).where(MembershipStore.membership_id == membership.id)).all()
        result.append({
            "membership_id": membership.id,
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": role.code,
            "role_name": role.name,
            "all_stores": membership.all_stores,
            "store_ids": store_ids,
            "active": user.active and membership.active,
        })
    return result


@router.post("/admin/users")
def create_user(data: TenantUserCreate, db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    role = db.scalar(select(Role).where(Role.company_id == context.company_id, Role.code == data.role_code, Role.active == True))
    if not role:
        raise HTTPException(400, "Perfil inválido")
    valid_store_ids = set(db.scalars(select(Store.id).where(Store.company_id == context.company_id, Store.active == True)).all())
    if not data.all_stores and (not data.store_ids or not set(data.store_ids).issubset(valid_store_ids)):
        raise HTTPException(400, "Selecione ao menos uma loja válida")
    try:
        user = User(
            username=data.username.strip(),
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            email=data.email,
            role=data.role_code,
        )
        db.add(user)
        db.flush()
        membership = Membership(user_id=user.id, company_id=context.company_id, role_id=role.id, all_stores=data.all_stores)
        db.add(membership)
        db.flush()
        if not data.all_stores:
            db.add_all([MembershipStore(membership_id=membership.id, store_id=store_id) for store_id in sorted(set(data.store_ids))])
        db.commit()
        return {"id": user.id, "membership_id": membership.id, "username": user.username, "role": role.code}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Nome de usuário já cadastrado")


@router.patch("/admin/users/{membership_id}")
def update_membership(membership_id: int, data: MembershipUpdate, db: Session = Depends(get_db), context=Depends(require("users.manage"))):
    membership = db.scalar(select(Membership).where(Membership.id == membership_id, Membership.company_id == context.company_id))
    if not membership:
        raise HTTPException(404, "Vínculo de usuário não encontrado")
    if membership.user_id == context.id and (not data.active or data.role_code != "admin"):
        raise HTTPException(409, "O administrador não pode remover ou rebaixar o próprio acesso atual")
    role = db.scalar(select(Role).where(Role.company_id == context.company_id, Role.code == data.role_code, Role.active == True))
    if not role:
        raise HTTPException(400, "Perfil inválido")
    valid_store_ids = set(db.scalars(select(Store.id).where(Store.company_id == context.company_id, Store.active == True)).all())
    if not data.all_stores and (not data.store_ids or not set(data.store_ids).issubset(valid_store_ids)):
        raise HTTPException(400, "Selecione ao menos uma loja válida")
    membership.role_id = role.id
    membership.all_stores = data.all_stores
    membership.active = data.active
    db.execute(delete(MembershipStore).where(MembershipStore.membership_id == membership.id))
    if not data.all_stores:
        db.add_all([MembershipStore(membership_id=membership.id, store_id=store_id) for store_id in sorted(set(data.store_ids))])
    user = db.get(User, membership.user_id)
    if user:
        user.role = role.code
        user.full_name = data.full_name
        user.email = data.email
        if data.new_password:
            user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True, "membership_id": membership.id, "role": role.code, "active": membership.active}
