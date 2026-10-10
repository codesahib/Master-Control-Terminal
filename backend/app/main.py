import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import APIKeyHeader

from app.api.routes import router as api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.finance import seed_contribution_limits, seed_reference_data

REQUESTED_WITH = "master-terminal"
api_token_header = APIKeyHeader(name="X-API-Token", auto_error=False)
requested_with_header = APIKeyHeader(name="X-Requested-With", auto_error=False)


def require_api_client(
    token: str | None = Security(api_token_header),
    requested_with: str | None = Security(requested_with_header),
) -> None:
    # A custom header forces a CORS preflight, which CORS_ORIGINS rejects for other sites.
    if settings.api_token:
        if not token or not secrets.compare_digest(token, settings.api_token):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Token header")
        return
    if requested_with != REQUESTED_WITH:
        raise HTTPException(status_code=403, detail=f"Missing X-Requested-With: {REQUESTED_WITH} header")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        seed_reference_data(db)
        seed_contribution_limits(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Master Terminal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Token", "X-Requested-With"],
    expose_headers=["Content-Disposition"],
)
# Added last so it runs first: blocks DNS-rebinding pages (Host: evil.example resolving to 127.0.0.1).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(api_router, dependencies=[Depends(require_api_client)])
