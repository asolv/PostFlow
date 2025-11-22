from fastapi import FastAPI
from app.core.cors import setup_cors
from app.core.config import settings
from app.api.v1.routers import rss as rss_router
from app.db.postgres import init_pool, close_pool

app = FastAPI(title=settings.APP_NAME, version="1.0.0")
setup_cors(app)

@app.on_event("startup")
def _startup():
    init_pool()

@app.on_event("shutdown")
def _shutdown():
    close_pool()

# API v1
app.include_router(rss_router.router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"ok": True, "app": settings.APP_NAME}
