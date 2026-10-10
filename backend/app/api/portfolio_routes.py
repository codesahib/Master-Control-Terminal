from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import PortfolioHealthRead, PortfolioHistoryPoint, PortfolioOverviewRead, SymbolCandidateRead, SymbolCreate
from app.services.market_data import save_symbol
from app.services.portfolio import portfolio_health, portfolio_history, portfolio_overview

router = APIRouter()


@router.get("/portfolio/overview", response_model=PortfolioOverviewRead)
def portfolio_overview_endpoint(
    year: int | None = Query(default=None),
    category_level: str = Query(default="precise", pattern="^(broad|precise)$"),
    currency: str = Query(default="CAD", pattern="^(CAD|USD)$"),
    db: Session = Depends(get_db),
):
    return portfolio_overview(db, year=year, category_level=category_level, currency=currency)


@router.get("/portfolio/health", response_model=PortfolioHealthRead)
def portfolio_health_endpoint(db: Session = Depends(get_db)):
    return portfolio_health(db)


@router.get("/portfolio/history", response_model=list[PortfolioHistoryPoint])
def portfolio_history_endpoint(
    days: int = Query(default=365, ge=1, le=3650),
    currency: str = Query(default="CAD", pattern="^(CAD|USD)$"),
    db: Session = Depends(get_db),
):
    return portfolio_history(db, days=days, currency=currency)


@router.post("/symbols", response_model=SymbolCandidateRead)
def save_symbol_endpoint(payload: SymbolCreate, db: Session = Depends(get_db)):
    try:
        return save_symbol(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
