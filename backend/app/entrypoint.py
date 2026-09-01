from .main import app
from .purge_test import router as purge_test_router
from .sales_line_discount import router as sales_line_discount_router
from .tenancy import router as tenancy_router

# O app principal ainda contém a rota histórica POST /sales.
# Removemos somente essa rota antes de registrar a versão consolidada,
# que entende desconto fixo em R$ como desconto total da linha.
app.router.routes = [
    route
    for route in app.router.routes
    if not (getattr(route, "path", None) == "/sales" and "POST" in (getattr(route, "methods", None) or set()))
]

app.include_router(sales_line_discount_router)
app.include_router(purge_test_router)
app.include_router(tenancy_router)
