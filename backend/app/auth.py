import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Company, Membership, MembershipStore, Permission, Role, RolePermission, Store, User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(password: str, hashed: str):
    return password_hash.verify(password, hashed)


@dataclass(frozen=True)
class TenantContext:
    user: User
    membership: Membership
    company: Company
    store: Store
    role_record: Role
    permissions: frozenset[str]

    @property
    def id(self):
        return self.user.id

    @property
    def username(self):
        return self.user.username

    @property
    def role(self):
        return self.role_record.code

    @property
    def company_id(self):
        return self.company.id

    @property
    def store_id(self):
        return self.store.id


def make_token(user: User, membership: Membership, store: Store):
    exp = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "480")))
    return jwt.encode(
        {
            "sub": str(user.id),
            "membership_id": membership.id,
            "company_id": membership.company_id,
            "store_id": store.id,
            "exp": exp,
        },
        os.environ["SECRET_KEY"],
        algorithm="HS256",
    )


def _membership_store_allowed(db: Session, membership: Membership, store_id: int) -> bool:
    store = db.scalar(
        select(Store).where(
            Store.id == store_id,
            Store.company_id == membership.company_id,
            Store.active == True,
        )
    )
    if not store:
        return False
    if membership.all_stores:
        return True
    return db.scalar(
        select(MembershipStore.id).where(
            MembershipStore.membership_id == membership.id,
            MembershipStore.store_id == store_id,
        )
    ) is not None


def resolve_login_context(db: Session, user: User, company_id: int | None = None, store_id: int | None = None):
    query = (
        select(Membership)
        .join(Company, Company.id == Membership.company_id)
        .where(Membership.user_id == user.id, Membership.active == True, Company.active == True)
    )
    if company_id is not None:
        query = query.where(Membership.company_id == company_id)
    membership = db.scalar(query.order_by(Membership.id))
    if not membership:
        raise HTTPException(403, "Usuário sem acesso a uma empresa ativa")

    stores_query = select(Store).where(Store.company_id == membership.company_id, Store.active == True)
    if not membership.all_stores:
        stores_query = stores_query.join(MembershipStore, MembershipStore.store_id == Store.id).where(
            MembershipStore.membership_id == membership.id
        )
    if store_id is not None:
        stores_query = stores_query.where(Store.id == store_id)
    store = db.scalar(stores_query.order_by(Store.id))
    if not store:
        raise HTTPException(403, "Usuário sem acesso a uma loja ativa")
    return membership, store


def current_context(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(creds.credentials, os.environ["SECRET_KEY"], algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        raise HTTPException(401, "Token inválido ou expirado")
    if not user or not user.active:
        raise HTTPException(401, "Usuário inválido")

    membership_id = payload.get("membership_id")
    if membership_id is None:
        # Compatibilidade durante o primeiro deploy: tokens antigos não carregam o tenant.
        membership, store = resolve_login_context(db, user)
    else:
        membership = db.scalar(
            select(Membership).where(
                Membership.id == int(membership_id),
                Membership.user_id == user.id,
                Membership.active == True,
            )
        )
        if not membership:
            raise HTTPException(401, "Acesso à empresa removido ou inativo")
        store_id = int(payload.get("store_id", 0))
        if not _membership_store_allowed(db, membership, store_id):
            raise HTTPException(403, "Acesso à loja removido ou inativo")
        store = db.get(Store, store_id)

    company = db.get(Company, membership.company_id)
    role = db.get(Role, membership.role_id)
    if not company or not company.active or not role or not role.active:
        raise HTTPException(403, "Contexto empresarial inativo")
    permissions = frozenset(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).all()
    )
    return TenantContext(user, membership, company, store, role, permissions)


# Alias temporário para integrações antigas. O retorno agora inclui o contexto tenant.
current_user = current_context
