from sqlalchemy import select
from sqlalchemy.orm import Session

from .finance import FinancialAccount, FinancialCategory
from .models import Company, Store
from .tenancy import seed_permissions_and_roles

DEFAULT_CATEGORIES = (
    ("VENDAS", "Receita de vendas", "REVENUE", "SALES"),
    ("OUTRAS_RECEITAS", "Outras receitas operacionais", "REVENUE", "OTHER_OPERATING_REVENUE"),
    ("FORNECEDORES", "Compras de mercadorias / fornecedores", "EXPENSE", "PURCHASES"),
    ("PESSOAL", "Pessoal e folha", "EXPENSE", "PERSONNEL"),
    ("OCUPACAO", "Aluguel, condomínio e ocupação", "EXPENSE", "OCCUPANCY"),
    ("UTILIDADES", "Água, energia, internet e utilidades", "EXPENSE", "UTILITIES"),
    ("TAXAS", "Taxas, tarifas e adquirência", "EXPENSE", "FEES"),
    ("IMPOSTOS", "Impostos e tributos", "EXPENSE", "TAXES"),
    ("OUTRAS_DESPESAS", "Outras despesas operacionais", "EXPENSE", "OTHER_OPERATING_EXPENSE"),
)


def seed_finance_defaults(db: Session):
    companies = db.scalars(select(Company).where(Company.active == True)).all()
    for company in companies:
        # Atualiza também empresas criadas antes da Fase 3.
        seed_permissions_and_roles(db, company)
        for code, name, nature, dre_group in DEFAULT_CATEGORIES:
            if not db.scalar(select(FinancialCategory.id).where(FinancialCategory.company_id == company.id, FinancialCategory.code == code)):
                db.add(FinancialCategory(company_id=company.id, code=code, name=name, nature=nature, dre_group=dre_group))
        for store in db.scalars(select(Store).where(Store.company_id == company.id, Store.active == True)).all():
            code = f"LOJA-{store.id}-CAIXA"
            if not db.scalar(select(FinancialAccount.id).where(FinancialAccount.company_id == company.id, FinancialAccount.code == code)):
                db.add(FinancialAccount(company_id=company.id, store_id=store.id, code=code, name=f"Disponibilidades - {store.name}", account_type="CASH", opening_balance=0))
    db.commit()
