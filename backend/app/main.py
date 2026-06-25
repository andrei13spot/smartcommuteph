# fastapi entrypoint.
# run: uvicorn app.main:app --reload --port 8000
# docs at http://127.0.0.1:8000/docs
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import API_DESCRIPTION, API_TITLE, API_VERSION, CORS_ORIGINS
from .routing.graph import load_graph


@asynccontextmanager
async def lifespan(_: FastAPI):
    # build and cache the graph at startup so the first request is quick
    load_graph()
    yield


app = FastAPI(
    title=API_TITLE, version=API_VERSION, description=API_DESCRIPTION, lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": API_TITLE, "version": API_VERSION, "docs": "/docs"}
