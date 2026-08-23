from .main import app
from .purge_test import router as purge_test_router

app.include_router(purge_test_router)
