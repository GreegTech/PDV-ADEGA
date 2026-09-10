import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import resolve_login_context
from app.database import Base
from app.finance import FinancialAccount, FinancialCategory
from app.finance_seed import DEFAULT_CATEGORIES
from app.models import Company, Membership, MembershipStore, Product, Store, StoreInventory, User
from app.schemas import CompanyCreate
from app.tenancy import create_company, ensure_default_tenant, role_permissions, seed_permissions_and_roles


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


def test_same_barcode_is_isolated_by_tenant(db):
    company_a, store_a, _ = create_company(db, "Empresa A", "empresa-a")
    company_b, store_b, _ = create_company(db, "Empresa B", "empresa-b")
    barcode = "7894900010015"
    db.add_all([
        Product(company_id=company_a.id, store_id=store_a.id, name="Produto A", barcode=barcode, cost=1, price=2),
        Product(company_id=company_b.id, store_id=store_b.id, name="Produto B", barcode=barcode, cost=1, price=2),
    ])
    db.commit()
    assert db.scalar(select(Product.name).where(Product.company_id == company_a.id)) == "Produto A"
    assert db.scalar(select(Product.name).where(Product.company_id == company_b.id)) == "Produto B"

    db.add(Product(company_id=company_a.id, store_id=store_a.id, name="Duplicado", barcode=barcode, cost=1, price=2))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_company_product_can_have_inventory_in_multiple_stores(db):
    company, store_a, _ = create_company(db, "Empresa", "empresa")
    store_b = Store(company_id=company.id, name="Filial", code="FILIAL")
    product = Product(company_id=company.id, name="Produto único", barcode="7894900010015", cost=0, price=0)
    db.add_all([store_b, product])
    db.flush()
    db.add_all([
        StoreInventory(company_id=company.id, store_id=store_a.id, product_id=product.id, stock=10, average_cost=4, price=8),
        StoreInventory(company_id=company.id, store_id=store_b.id, product_id=product.id, stock=3, average_cost=4.5, price=9),
    ])
    db.commit()
    assert db.scalar(select(func.count(Product.id)).where(Product.company_id == company.id)) == 1
    assert db.scalar(select(func.count(StoreInventory.id)).where(StoreInventory.product_id == product.id)) == 2


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


def test_new_company_is_created_with_finance_defaults(db):
    admin = User(
        username="platform-admin",
        password_hash="hash",
        role="admin",
        is_platform_admin=True,
    )
    db.add(admin)
    db.commit()

    context = type("Context", (), {"id": admin.id, "user": admin})()
    result = create_company(
        CompanyCreate(name="Empresa Nova", slug="empresa-nova", store_name="Matriz"),
        db,
        context,
    )

    categories = db.scalars(
        select(FinancialCategory).where(FinancialCategory.company_id == result["id"])
    ).all()
    accounts = db.scalars(
        select(FinancialAccount).where(FinancialAccount.company_id == result["id"])
    ).all()
    roles = seed_permissions_and_roles(db, db.get(Company, result["id"]))

    assert len(categories) == len(DEFAULT_CATEGORIES) == 9
    assert len(accounts) == 1
    assert accounts[0].store_id == result["store_id"]
    assert accounts[0].code == f"LOJA-{result['store_id']}-CAIXA"
    for role_code in ("admin", "manager"):
        permissions = role_permissions(db, roles[role_code].id)
        assert {"finance.read", "finance.write", "finance.settle", "finance.reports"} <= permissions


def test_company_creation_rolls_back_when_finance_provisioning_fails(db, monkeypatch):
    admin = User(
        username="platform-admin",
        password_hash="hash",
        role="admin",
        is_platform_admin=True,
    )
    db.add(admin)
    db.commit()
    context = type("Context", (), {"id": admin.id, "user": admin})()

    def fail_provisioning(session, company):
        raise RuntimeError("falha simulada no provisionamento financeiro")

    monkeypatch.setattr(
        "app.finance_seed.seed_finance_defaults_for_company",
        fail_provisioning,
    )

    with pytest.raises(RuntimeError, match="falha simulada"):
        create_company(
            CompanyCreate(
                name="Empresa Incompleta",
                slug="empresa-incompleta",
                store_name="Matriz",
            ),
            db,
            context,
        )

    assert db.scalar(select(Company.id).where(Company.slug == "empresa-incompleta")) is None
