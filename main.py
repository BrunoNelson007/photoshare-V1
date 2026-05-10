"""
PhotoShare API — main.py
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from config import get_settings
from security import limiter, security_headers_middleware
from posts import router as posts_router
from comments import router as comments_router
from ratings import router as ratings_router
from users import router as users_router
from azure_clients import close_clients, get_cosmos_client, get_blob_service

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_cosmos_client()
    get_blob_service()
    print("✅ Azure clients initialised")
    yield
    await close_clients()
    print("🛑 Azure clients closed")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please slow down."},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    if settings.debug:
        raise exc
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred."})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.middleware("http")(security_headers_middleware)

app.include_router(users_router)
app.include_router(posts_router)
app.include_router(comments_router)
app.include_router(ratings_router)


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/ready", tags=["ops"])
async def ready():
    try:
        db = get_cosmos_client().get_database_client(settings.cosmos_database)
        await db.read()
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
