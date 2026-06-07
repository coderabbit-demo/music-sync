from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth.router import router as auth_router
from app.api.playlists.router import router as playlists_router
from app.api.sync.router import router as sync_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Nothing to initialise at startup — migrations run via `alembic upgrade head`
    yield


app = FastAPI(
    title="music-sync",
    description="Synchronize playlists between Spotify and YouTube Music",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/music", tags=["auth"])
app.include_router(playlists_router, prefix="/api/playlists", tags=["playlists"])
app.include_router(sync_router, prefix="/api/sync", tags=["sync"])


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
