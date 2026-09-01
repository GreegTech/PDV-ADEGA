import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import resolve_login_context
from app.database import Base
from app.models import Company, Membership, MembershipStore, Product, Store, User
from app.tenancy import ensure_default_tenant, role_permissions, seed_permissions_and_roles


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_company(db, name, slug):
    company = Company(name=name, slug=slug)
    db.add(company)
    db.flush()
    store = Store(company_id=company.id, name="Matriz", code="MATRIZ")
    db.add(store)
    db.flush()
    roles = seed_permissions_and_roles(db, company)
    return company, store, roles


def test_same_barcode_is_isolated_by_store_and_tenant(db):
    company_a, store_a, _ = create_company(db, "Empresa A", "empresa-a")
    company_b, store_b, _ = create_company(db, "Empresa B", "empresa-b")
    barcode = "7894900010015"
    db.add_all([
        Product(company_id=company_a.id, store_id=store_a.id, name="Produto A", barcode=barcode, cost=1, price=2),
        Product(company_id=company_b.id, store_id=store_b.id, name="Produto B", barcode=barcode, cost=1, price=2),
    ])
    db.commit()
    assert db.scalar(select(Product.name).where(Product.store_id == store_a.id)) == "Produto A"
    assert db.scalar(select(Product.name).where(Product.store_id == store_b.id)) == "Produto B"

    db.add(Product(company_id=company_a.id, store_id=store_a.id, name="Duplicado", barcode=barcode, cost=1, price=2))
    with pytest.raises(IntegrityError):
        db.commit()


def test_operator_has_only_operational_permissions(db):
    company, _, roles = create_company(db, "Empresa", "empresa")
    db.commit()
    permissions = role_permissions(db, roles["operator"].id)
    assert "sales.create" in permissions
    assert "products.read" in permissions
    assert "companies.manage" not in permissions
    assert "users.manage" not in permissions
    assert db.scalar(select(Company.id).where(Company.id == company.id)) == company.id


def test_restricted_membership_cannot_select_another_store(db):
    company, allowed_store, roles = create_company(db, "Empresa", "empresa")
    blocked_store = Store(company_id=company.id, name="Filial", code="FILIAL")
    user = User(username="operador", password_hash="hash", role="operator")
    db.add_all([blocked_store, user])
    db.flush()
    membership = Membership(user_id=user.id, company_id=company.id, role_id=roles["operator"].id, all_stores=False)
    db.add(membership)
    db.flush()
    db.add(MembershipStore(membership_id=membership.id, store_id=allowed_store.id))
    db.commit()

    resolved_membership, resolved_store = resolve_login_context(db, user, company.id, allowed_store.id)
    assert resolved_membership.id == membership.id
    assert resolved_store.id == allowed_store.id

    with pytest.raises(HTTPException) as exc:
        resolve_login_context(db, user, company.id, blocked_store.id)
    assert exc.value.status_code == 403


def test_legacy_users_are_migrated_to_default_company(db):
    admin = User(username="admin", password_hash="hash", role="admin")
    operator = User(username="caixa", password_hash="hash", role="operator")
    db.add_all([admin, operator])
    db.commit()

    company, store, admin_membership = ensure_default_tenant(db, admin)
    operator_membership = db.scalar(
        select(Membership).where(Membership.user_id == operator.id, Membership.company_id == company.id)
    )
    assert admin_membership.all_stores is True
    assert operator_membership is not None
    assert operator_membership.all_stores is False
    assert db.scalar(
        select(MembershipStore.id).where(
            MembershipStore.membership_id == operator_membership.id,
            MembershipStore.store_id == store.id,
        )
    ) is not None
