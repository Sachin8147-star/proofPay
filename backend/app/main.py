import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import admin, assistant, indexer, keeper, market, routes, wallet
from .config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_):
    indexer.start()
    keeper.start()
    yield


_docs = None if settings.env == "production" else "/docs"
app = FastAPI(title="ProofPay API", lifespan=lifespan, docs_url=_docs, redoc_url=None, openapi_url=None if _docs is None else "/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.web_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(routes.router)
app.include_router(market.router)
app.include_router(wallet.router)
app.include_router(assistant.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"ok": True}
