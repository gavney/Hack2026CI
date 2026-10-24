from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
import pandas as pd

from backend.database import get_db
from backend.models import Operation, Company
from backend.core.analytics import calculate_analytics

router = APIRouter(tags=["Финансовая Аналитика ДДС"])

@router.get("/companies/{company_id}/analytics")
def get_analytics(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    ops = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date).all()
    if not ops:
        return {
            "total_inflow": 0.0,
            "total_outflow": 0.0,
            "net_flow": 0.0,
            "inflow_categories": [],
            "outflow_categories": [],
            "monthly_dynamics": [],
            "owner_draw_summary": {"withdrawn_by_owner": 0.0, "retained_in_business": 0.0, "share_of_net": 0.0},
            "top_counterparties": [],
            "concentration_warning": None,
            "safety_runway_days": 0,
            "company_name": comp.name,
            "inn": comp.inn,
            "industry": comp.industry,
            "overdraft_limit": comp.overdraft_limit or 0.0,
            "has_statement": comp.has_statement
        }

    ops_df = pd.DataFrame([{
        "operation_date": op.operation_date,
        "amount": op.amount,
        "direction": op.direction,
        "category_id": op.category_id,
        "counterparty_inn": op.counterparty_inn,
        "counterparty_name": op.counterparty_name,
        "balance_eod": op.balance_eod
    } for op in ops])

    res = calculate_analytics(ops_df)
    res["company_name"] = comp.name
    res["inn"] = comp.inn
    res["industry"] = comp.industry
    res["overdraft_limit"] = comp.overdraft_limit or 0.0
    return res
