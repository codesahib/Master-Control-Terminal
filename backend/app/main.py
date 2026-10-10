from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.db.session import SessionLocal
from app.services.finance import seed_contribution_limits, seed_reference_data

app = FastAPI(title="Master Terminal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        seed_reference_data(db)
        seed_contribution_limits(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(api_router)
