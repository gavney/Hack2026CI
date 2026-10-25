from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, timedelta
import uuid

from backend.database import get_db
from backend.models import Scenario, Company
from backend.schemas import ScenarioOut, ScenarioCreate, ScenarioUpdate
from backend.routers.forecast import get_company_forecast

router = APIRouter(tags=["Сценарии «Что если»"])

DEFAULT_SCENARIOS = [
    {
        "id": "scen_delay_client",
        "name": "Крупный клиент задержит оплату на 2 недели",
        "scenario_type": "delayed_payment",
        "params": {"delay_days": 14}
    },
    {
        "id": "scen_rev_drop_20",
        "name": "Падение выручки на 20%",
        "scenario_type": "revenue_drop",
        "params": {"drop_percent": 20.0}
    },
    {
        "id": "scen_unexp_expense",
        "name": "Внеплановый крупный расход (250 000 ₽)",
        "scenario_type": "unexpected_expense",
        "params": {"amount": 250000.0}
    },
    {
        "id": "scen_cost_hike_15",
        "name": "Рост постоянных расходов на 15%",
        "scenario_type": "cost_increase",
        "params": {"increase_percent": 15.0}
    }
]

@router.get("/companies/{company_id}/scenarios", response_model=List[ScenarioOut])
def list_scenarios(company_id: str, db: Session = Depends(get_db)):
    scens = db.query(Scenario).filter(Scenario.company_id == company_id).all()
    if not scens:
        # Seed default 4 scenarios for the company
        for ds in DEFAULT_SCENARIOS:
            sc = Scenario(
                id=f"{ds['id']}_{company_id}",
                company_id=company_id,
                name=ds["name"],
                scenario_type=ds["scenario_type"],
                params=ds["params"]
            )
            db.add(sc)
        db.commit()
        scens = db.query(Scenario).filter(Scenario.company_id == company_id).all()
    return scens

@router.post("/companies/{company_id}/scenarios", response_model=ScenarioOut)
def create_scenario(company_id: str, payload: ScenarioCreate, db: Session = Depends(get_db)):
    sc = Scenario(
        id=f"scen_{uuid.uuid4().hex[:8]}_{company_id}",
        company_id=company_id,
        name=payload.name,
        scenario_type=payload.scenario_type,
        params=payload.params
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return sc

@router.patch("/companies/{company_id}/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(
    company_id: str,
    scenario_id: str,
    payload: ScenarioUpdate,
    db: Session = Depends(get_db)
):
    sc = db.query(Scenario).filter(
        Scenario.company_id == company_id,
        Scenario.id == scenario_id
    ).first()
    if not sc:
        raise HTTPException(status_code=404, detail="Сценарий не найден")

    if payload.name is not None:
        sc.name = payload.name
    if payload.params is not None:
        new_params = dict(sc.params or {})
        new_params.update(payload.params)
        sc.params = new_params
    if payload.is_active is not None:
        sc.is_active = payload.is_active

    db.commit()
    db.refresh(sc)
    return sc

@router.get("/companies/{company_id}/scenarios/{scenario_id}/compare")
def compare_scenario(
    company_id: str,
    scenario_id: str,
    horizon: int = Query(30, ge=7, le=90),
    delay_days: Optional[int] = Query(None),
    drop_percent: Optional[float] = Query(None),
    amount: Optional[float] = Query(None),
    increase_percent: Optional[float] = Query(None),
    expense_days_ahead: Optional[int] = Query(None),
    model: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Simulates baseline vs scenario side-by-side (FR-8.5):
    Returns both curves on the same calendar timeline and delta metrics.
    Supports real-time parameter override via query parameters.
    """
    # 1. Resolve scenario record
    sc = db.query(Scenario).filter(
        Scenario.company_id == company_id,
        (Scenario.id == scenario_id) | (Scenario.id == f"{scenario_id}_{company_id}")
    ).first()

    if not sc:
        # Auto-seed if it matches a default template
        for ds in DEFAULT_SCENARIOS:
            if ds["id"] == scenario_id or f"{ds['id']}_{company_id}" == scenario_id:
                sc = Scenario(
                    id=f"{ds['id']}_{company_id}",
                    company_id=company_id,
                    name=ds["name"],
                    scenario_type=ds["scenario_type"],
                    params=dict(ds["params"])
                )
                db.add(sc)
                db.commit()
                db.refresh(sc)
                break

    # 2. Dynamic parameter overrides
    if sc:
        params_updated = False
        new_params = dict(sc.params or {})
        if delay_days is not None:
            new_params["delay_days"] = int(delay_days)
            params_updated = True
        if drop_percent is not None:
            new_params["drop_percent"] = float(drop_percent)
            params_updated = True
        if amount is not None:
            new_params["amount"] = float(amount)
            params_updated = True
        if increase_percent is not None:
            new_params["increase_percent"] = float(increase_percent)
            params_updated = True
        if expense_days_ahead is not None:
            new_params["expense_days_ahead"] = int(expense_days_ahead)
            params_updated = True

        if params_updated:
            sc.params = new_params
            db.commit()
            db.refresh(sc)

    target_scen_id = sc.id if sc else scenario_id

    # 3. Compute baseline and scenario forecasts using target model (default canonical ML)
    comp = db.query(Company).filter(Company.id == company_id).first()
    target_model = model or (comp.forecast_model if comp and comp.forecast_model else "ml-v2.0-canonical")
    baseline = get_company_forecast(company_id=company_id, horizon=horizon, scenario_id=None, model=target_model, db=db)
    scenario_fc = get_company_forecast(company_id=company_id, horizon=horizon, scenario_id=target_scen_id, model=target_model, db=db)

    # 4. Compare days
    comparison = []
    base_days = {d["date"]: d for d in baseline["days"]}
    for sd in scenario_fc["days"]:
        d_date = sd["date"]
        bd = base_days.get(d_date, {})
        base_p50 = bd.get("p50", 0.0)
        scen_p50 = sd["p50"]
        diff = scen_p50 - base_p50
        comparison.append({
            "date": d_date,
            "baseline_p50": base_p50,
            "scenario_p50": scen_p50,
            "difference": round(diff, 2),
            "baseline_p10": bd.get("p10", 0.0),
            "scenario_p10": sd["p10"],
            "scenario_gap_prob": sd["prob_negative"]
        })

    base_min = min((d["p50"] for d in baseline["days"]), default=0.0)
    scen_min = min((d["p50"] for d in scenario_fc["days"]), default=0.0)
    base_end = baseline["days"][-1]["p50"] if baseline.get("days") else 0.0
    scen_end = scenario_fc["days"][-1]["p50"] if scenario_fc.get("days") else 0.0

    return {
        "scenario_id": target_scen_id,
        "scenario_name": sc.name if sc else scenario_id,
        "scenario_type": sc.scenario_type if sc else "custom",
        "params": sc.params if sc else {},
        "horizon": horizon,
        "baseline_first_gap": baseline.get("first_gap_date"),
        "scenario_first_gap": scenario_fc.get("first_gap_date"),
        "baseline_shortfall": baseline.get("total_shortfall_p10", 0.0),
        "scenario_shortfall": scenario_fc.get("total_shortfall_p10", 0.0),
        "baseline_min_balance": round(base_min, 2),
        "scenario_min_balance": round(scen_min, 2),
        "baseline_end_balance": round(base_end, 2),
        "scenario_end_balance": round(scen_end, 2),
        "comparison": comparison
    }
