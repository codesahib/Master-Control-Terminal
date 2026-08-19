from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.api.routes import router as api_router
from app.db.session import SessionLocal
from app.models.models import Account, ContributionLimit
from app.services.finance import seed_reference_data

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
    seed_reference_data(db)

    # Seed baseline limits for current years when missing.
    seeded = {
        "RRSP": {2024: 16840, 2025: 17324, 2026: 0},
        "FHSA": {2024: 8000, 2025: 8000, 2026: 8000},
        "TFSA": {2024: 7000, 2025: 7000, 2026: 7000},
    }
    seeded_limit_count = db.scalar(select(func.count(ContributionLimit.id))) or 0
    if seeded_limit_count >= sum(len(years) for years in seeded.values()):
        db.close()
        return

    for account_name, years in seeded.items():
        account = db.scalar(select(Account).where(Account.name == account_name))
        if not account:
            continue
        for year, new in years.items():
            tax_year = str(year)
            existing = db.scalar(
                select(ContributionLimit).where(
                    ContributionLimit.account_id == account.id,
                    ContributionLimit.tax_year == tax_year,
                )
            )
            if not existing:
                db.add(
                    ContributionLimit(
                        account_id=account.id,
                        tax_year=tax_year,
                        new_room=new,
                    )
                )
    db.commit()
    db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(api_router)
