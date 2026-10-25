import pandas as pd
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid

from backend.database import get_db
from backend.models import Company, Operation, Slot, Event, Forecast, ForecastDay, Alert, Scenario, Counterparty
from backend.schemas import ForecastResultOut, AlertOut, ForecastSettingsOut, ForecastSettingsUpdate
from backend.core.forecaster import ForecasterStubV01, MonteCarloForecaster, MLForecaster
from backend.core.risk import evaluate_cash_gap
from backend.core.slots import next_business_day

router = APIRouter(tags=["Прогнозирование и Риски"])

# --- Pluggable Forecaster Registry ---
FORECASTER_REGISTRY = {
    "ml-v2.0-canonical": MLForecaster(),
    "ml-ridge-lgbm": MLForecaster(),
    "ml": MLForecaster(),
    "monte-carlo": MonteCarloForecaster(n_simulations=1000, n_sample_paths=5),
    "stub-0.1": ForecasterStubV01(k_factor=1.28),
}
DEFAULT_MODEL = "ml-v2.0-canonical"


@router.get("/companies/{company_id}/forecast-settings", response_model=ForecastSettingsOut)
def get_forecast_settings(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    
    from backend.core.ai_categorizer import gigachat_client
    is_connected = gigachat_client.is_available()

    return ForecastSettingsOut(
        forecast_model=comp.forecast_model or DEFAULT_MODEL,
        forecast_simulations=comp.forecast_simulations or 1000,
        forecast_confidence_level=comp.forecast_confidence_level or 0.90,
        ml_categorizer_threshold=comp.ml_categorizer_threshold or 0.60,
        gigachat_enabled=bool(comp.gigachat_enabled),
        gigachat_connected=is_connected,
        available_models=list(FORECASTER_REGISTRY.keys())
    )


@router.patch("/companies/{company_id}/forecast-settings", response_model=ForecastSettingsOut)
def update_forecast_settings(
    company_id: str,
    payload: ForecastSettingsUpdate,
    db: Session = Depends(get_db)
):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    if payload.forecast_model is not None:
        if payload.forecast_model not in FORECASTER_REGISTRY:
            raise HTTPException(status_code=400, detail=f"Недопустимая модель прогноза. Доступные: {list(FORECASTER_REGISTRY.keys())}")
        comp.forecast_model = payload.forecast_model

    if payload.forecast_simulations is not None:
        comp.forecast_simulations = max(100, min(10000, payload.forecast_simulations))
    if payload.forecast_confidence_level is not None:
        comp.forecast_confidence_level = max(0.50, min(0.99, payload.forecast_confidence_level))
    if payload.ml_categorizer_threshold is not None:
        comp.ml_categorizer_threshold = max(0.30, min(0.95, payload.ml_categorizer_threshold))
    if payload.gigachat_enabled is not None:
        comp.gigachat_enabled = payload.gigachat_enabled
    if payload.gigachat_credentials is not None:
        comp.gigachat_credentials = payload.gigachat_credentials

    db.commit()
    db.refresh(comp)

    from backend.core.ai_categorizer import gigachat_client
    is_connected = gigachat_client.is_available()

    return ForecastSettingsOut(
        forecast_model=comp.forecast_model,
        forecast_simulations=comp.forecast_simulations,
        forecast_confidence_level=comp.forecast_confidence_level,
        ml_categorizer_threshold=comp.ml_categorizer_threshold,
        gigachat_enabled=bool(comp.gigachat_enabled),
        gigachat_connected=is_connected,
        available_models=list(FORECASTER_REGISTRY.keys())
    )


@router.get("/companies/{company_id}/forecast", response_model=ForecastResultOut)
def get_company_forecast(
    company_id: str,
    horizon: int = Query(30, ge=7, le=90),
    scenario_id: Optional[str] = None,
    model: Optional[str] = Query(None, description="Forecasting model: ml-ridge-lgbm | monte-carlo | stub-0.1"),
    db: Session = Depends(get_db)
):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    # If model is explicitly passed in query string, honor it! Only fall back to company setting if omitted.
    if not model:
        model = comp.forecast_model or DEFAULT_MODEL
    elif model not in FORECASTER_REGISTRY:
        model = DEFAULT_MODEL

    if not isinstance(horizon, int):
        horizon = 30

    # Fetch last operations to determine as_of and balance
    ops = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date).all()
    if ops:
        history_records = [{
            "operation_date": op.operation_date,
            "amount": op.amount,
            "direction": op.direction,
            "category_id": op.category_id,
            "balance_eod": op.balance_eod,
            "payment_purpose": op.payment_purpose,
            "counterparty_name": op.counterparty_name,
            "counterparty_inn": op.counterparty_inn
        } for op in ops]
        history_df = pd.DataFrame(history_records)
        last_op = ops[-1]
        as_of = last_op.operation_date
        # Если задан отредактированный остаток (!= 0), используем его; иначе остаток по файлу на последний расчетный день
        if comp.initial_manual_balance is not None and comp.initial_manual_balance != 0:
            balance_as_of = float(comp.initial_manual_balance)
        else:
            balance_as_of = float(last_op.balance_eod)
        is_clean_business = False
    else:
        # «Чистый бизнес» без загруженной выписки (онбординг)
        history_df = pd.DataFrame()
        as_of = date.today()
        balance_as_of = float(comp.initial_manual_balance or comp.last_balance or 0.0)
        is_clean_business = True

    # Gather future events
    events_payload = []

    # 1. Projected recurring slots across horizon
    active_slots = db.query(Slot).filter(Slot.company_id == company_id, Slot.is_active == True).all()
    slots_dicts = []
    for slot in active_slots:
        slots_dicts.append({
            "category_id": slot.category_id,
            "typical_amount": slot.typical_amount,
            "day_of_month": slot.day_of_month,
            "direction": slot.direction
        })

        # Project slot forward for months in horizon
        start_date = as_of + timedelta(days=1)
        end_date = as_of + timedelta(days=horizon)
        cur_year = start_date.year
        cur_month = start_date.month

        while True:
            # Construct target date for month
            try:
                # Handle shorter months
                day_target = min(slot.day_of_month, 28 if cur_month == 2 else 30)
                proj_date = date(cur_year, cur_month, day_target)
                if proj_date > end_date:
                    break
                if proj_date >= start_date:
                    signed_amt = slot.typical_amount if slot.direction == 'Поступление' else -slot.typical_amount
                    events_payload.append({
                        "event_date": proj_date,
                        "amount": signed_amt,
                        "probability": 1.0,
                        "category_id": slot.category_id,
                        "counterparty_inn": slot.counterparty_inn,
                        "counterparty_name": slot.counterparty_name,
                        "source": "slot",
                        "note": f"Регулярный платеж: {slot.category_id}"
                    })
            except ValueError:
                pass

            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1

    # 2. Add manual, invoice, contract, and integrated events
    future_events = db.query(Event).filter(
        Event.company_id == company_id,
        Event.event_date > as_of,
        Event.event_date <= as_of + timedelta(days=horizon),
        (Event.is_active == True) | (Event.is_active == None)
    ).all()

    for ev in future_events:
        events_payload.append({
            "event_date": ev.event_date,
            "amount": ev.amount,
            "probability": ev.probability,
            "category_id": ev.category_id,
            "counterparty_inn": ev.counterparty_inn,
            "counterparty_name": ev.counterparty_name,
            "source": ev.source,
            "note": ev.note
        })

    # 2.5 Apply FNS risk adjustments (nalogbi + check) for counterparties with include_in_forecast == True
    blocked_counterparties = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.include_in_forecast == True,
        (Counterparty.has_blocks == True) | (Counterparty.risk_level == 'red')
    ).all()

    blocked_inns = {cp.inn: cp for cp in blocked_counterparties}
    fns_affected_debtors = []

    if blocked_inns:
        # Check if any future incoming event is from a blocked debtor
        for ev in events_payload:
            c_inn = ev.get("counterparty_inn")
            if c_inn and c_inn in blocked_inns and ev.get("amount", 0) > 0:
                cp = blocked_inns[c_inn]
                orig_date = ev["event_date"] if isinstance(ev["event_date"], date) else pd.to_datetime(ev["event_date"]).date()
                ev["event_date"] = orig_date + timedelta(days=21)
                ev["probability"] = 0.35  # High risk of non-payment due to FNS block
                ev["source"] = "fns_risk_delayed"
                ev["note"] = f"Задержка 21 дн: счет дебитора заблокирован ФНС (ст. 76 НК РФ)"
                fns_affected_debtors.append(f"{cp.name} (ИНН {cp.inn})")

    # 3. Check scenario
    scenario_dict = None
    if scenario_id:
        scen = db.query(Scenario).filter(
            (Scenario.id == scenario_id) | 
            ((Scenario.company_id == company_id) & (Scenario.id == f"{scenario_id}_{company_id}"))
        ).first()
        if scen:
            scenario_dict = {
                "scenario_type": scen.scenario_type,
                "params": scen.params
            }
        else:
            from backend.routers.scenarios import DEFAULT_SCENARIOS
            for ds in DEFAULT_SCENARIOS:
                if ds["id"] == scenario_id or f"{ds['id']}_{company_id}" == scenario_id:
                    scenario_dict = {
                        "scenario_type": ds["scenario_type"],
                        "params": ds["params"]
                    }
                    break

    # 4. Select forecasting model from registry
    if model == "monte-carlo":
        forecaster = MonteCarloForecaster(
            n_simulations=comp.forecast_simulations or 1000,
            n_sample_paths=5
        )
    elif model in ["ml-v2.0-canonical", "ml-ridge-lgbm", "ml"]:
        forecaster = MLForecaster()
    elif model == "stub-0.1":
        forecaster = ForecasterStubV01(k_factor=1.28)
    else:
        forecaster = FORECASTER_REGISTRY.get(model, MLForecaster())

    # Execute Forecast
    eff_overdraft = float(comp.overdraft_limit or 0.0)
    result = forecaster.forecast(
        history=history_df,
        balance_as_of=balance_as_of,
        as_of=as_of,
        horizon=horizon,
        events=events_payload,
        scenario=scenario_dict,
        overdraft_limit=eff_overdraft,
        detected_slots=slots_dicts,
        seed=42
    )

    if is_clean_business:
        result["model_version"] = "clean-business"
        result["quality"] = "new_business"

    # Risk evaluation strictly using canonical MLForecaster (ml-v2.0-canonical)
    if model != "ml-v2.0-canonical" and not is_clean_business:
        canonical_forecaster = MLForecaster()
        canonical_res = canonical_forecaster.forecast(
            history=history_df,
            balance_as_of=balance_as_of,
            as_of=as_of,
            horizon=horizon,
            events=events_payload,
            scenario=scenario_dict,
            overdraft_limit=eff_overdraft,
            detected_slots=slots_dicts,
            seed=42
        )
        radar_target = canonical_res
    else:
        radar_target = result

    gap_eval = evaluate_cash_gap(
        forecast_result=radar_target,
        mandatory_slots=slots_dicts,
        overdraft_limit=eff_overdraft
    )
    result["risk_radar"] = gap_eval

    if gap_eval:
        # Save or update alert
        existing_alert = db.query(Alert).filter(
            Alert.company_id == company_id,
            Alert.acknowledged == False
        ).first()

        if existing_alert:
            existing_alert.level = gap_eval["level"]
            existing_alert.gap_date = gap_eval["gap_date"]
            existing_alert.shortfall_p10 = gap_eval["shortfall_p10"]
            existing_alert.shortfall_p50 = gap_eval["shortfall_p50"]
            existing_alert.probability = gap_eval["probability"]
            existing_alert.reason = gap_eval["reason"]
            existing_alert.actions = gap_eval["actions"]
        else:
            new_alert = Alert(
                id=gap_eval["id"],
                company_id=company_id,
                level=gap_eval["level"],
                gap_date=gap_eval["gap_date"],
                shortfall_p10=gap_eval["shortfall_p10"],
                shortfall_p50=gap_eval["shortfall_p50"],
                probability=gap_eval["probability"],
                reason=gap_eval["reason"],
                actions=gap_eval["actions"]
            )
            db.add(new_alert)
        db.commit()

    if "simulation_meta" not in result or result["simulation_meta"] is None:
        result["simulation_meta"] = {}
    result["simulation_meta"]["fns_risk_active"] = len(fns_affected_debtors) > 0
    result["simulation_meta"]["fns_affected_debtors"] = list(set(fns_affected_debtors))

    return result

@router.get("/companies/{company_id}/risk-radar")
def get_company_risk_radar(
    company_id: str,
    horizon: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """Returns real-time Risk Radar evaluated strictly by canonical ML model (ml-v2.0-canonical)."""
    fc = get_company_forecast(company_id=company_id, horizon=horizon, model="ml-v2.0-canonical", db=db)
    return fc.get("risk_radar") or {}

@router.get("/companies/{company_id}/alerts", response_model=List[AlertOut])
def get_company_alerts(company_id: str, db: Session = Depends(get_db)):
    alerts = db.query(Alert).filter(Alert.company_id == company_id).order_by(Alert.created_at.desc()).all()
    if not alerts:
        # Pre-calculate forecast on first alerts query to evaluate cash gap if operations exist
        try:
            get_company_forecast(company_id=company_id, horizon=30, model="ml-v2.0-canonical", db=db)
            alerts = db.query(Alert).filter(Alert.company_id == company_id).order_by(Alert.created_at.desc()).all()
        except Exception:
            pass
    return alerts

@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Предупреждение не найдено")
    alert.acknowledged = True
    db.commit()
    return {"status": "ok", "message": "Предупреждение отмечено как прочитанное"}


@router.get("/models")
def list_available_models():
    """List all registered forecasting models with metadata."""
    models = []
    for key, forecaster in FORECASTER_REGISTRY.items():
        meta = {
            "id": key,
            "is_default": key == DEFAULT_MODEL,
        }
        if isinstance(forecaster, MonteCarloForecaster):
            meta["name"] = "Монте-Карло"
            meta["description"] = f"{forecaster.n_simulations} симуляций • Bootstrap по дням недели • VaR/CVaR • P10/P50/P90"
            meta["icon"] = "⚡"
            meta["quality"] = "medium"
            meta["version"] = "monte-carlo-v1.0"
        elif isinstance(forecaster, ForecasterStubV01):
            meta["name"] = "Статистический (stub)"
            meta["description"] = "Среднее + σ√t коридор • Normal CDF • Быстрый"
            meta["icon"] = "📊"
            meta["quality"] = "low"
            meta["version"] = "stub-0.1"
        else:
            meta["name"] = key
            meta["description"] = "Custom model"
            meta["icon"] = "🔧"
            meta["quality"] = "unknown"
            meta["version"] = key
        models.append(meta)
    return {"models": models, "default": DEFAULT_MODEL}
