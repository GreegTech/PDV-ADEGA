from . import tenancy

FINANCE_PERMISSIONS = {
    "finance.read": ("Consultar contas a pagar e receber", "finance"),
    "finance.write": ("Cadastrar e editar lançamentos financeiros", "finance"),
    "finance.settle": ("Realizar baixas financeiras", "finance"),
    "finance.reports": ("Consultar fluxo de caixa e DRE", "finance"),
}

# O seed multi-tenant roda no startup. Este módulo é importado pelo entrypoint
# antes do startup, ampliando os templates sem duplicar a lógica de RBAC.
tenancy.PERMISSIONS.update(FINANCE_PERMISSIONS)
tenancy.ROLE_TEMPLATES["admin"]["permissions"].update(FINANCE_PERMISSIONS)
tenancy.ROLE_TEMPLATES["manager"]["permissions"].update(FINANCE_PERMISSIONS)
