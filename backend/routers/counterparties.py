import os
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from backend.database import get_db
from backend.models import Company, Counterparty, Operation, Event
from backend.schemas import (
    CounterpartyOut, CounterpartyCheckRequest, CounterpartyCreateRequest,
    CounterpartyToggleForecastRequest, FnsApiKeyRequest
)
from backend.core.integrations.adapter_fns import AdapterFNSNalog
from backend.config import settings

router = APIRouter(tags=["Контрагенты и ФНС (nalogbi + check)"])
fns_adapter = AdapterFNSNalog()


def _ensure_company_counterparties(company_id: str, db: Session):
    """Auto-populates counterparties from historical operations and future events if not yet stored"""
    existing_count = db.query(Counterparty).filter(Counterparty.company_id == company_id).count()
    if existing_count > 0:
        return

    # Find distinct counterparties with meaningful turnover
    op_stats = db.query(
        Operation.counterparty_inn,
        Operation.counterparty_name,
        func.sum(Operation.amount).label("turnover"),
        func.count(Operation.id).label("ops_count"),
        func.max(Operation.operation_date).label("last_op_date")
    ).filter(
        Operation.company_id == company_id,
        Operation.counterparty_inn.isnot(None),
        Operation.counterparty_inn != ""
    ).group_by(
        Operation.counterparty_inn
    ).order_by(
        desc("turnover")
    ).limit(25).all()

    for stat in op_stats:
        inn = stat[0]
        name = stat[1] or f"Контрагент ИНН {inn}"
        if "@" in str(name):
            # В выписке вместо названия контрагента стояла почта — пытаемся взять официальное наименование из ФНС
            if settings.FNS_API_KEY:
                try:
                    s_data = fns_adapter.fetch_search(inn)
                    if s_data and "items" in s_data:
                        for it in s_data["items"]:
                            ent = it.get("ЮЛ") or it.get("ИП") or {}
                            if str(ent.get("ИНН", "")).strip() == str(inn).strip():
                                real_n = (ent.get("НаимСокрЮЛ") or ent.get("НаимПолнЮЛ") or ent.get("ФИОПолн") or "").strip()
                                if real_n:
                                    name = real_n
                                break
                except Exception:
                    pass
        turnover = float(stat[2] or 0.0)
        ops_cnt = int(stat[3] or 1)
        last_dt = stat[4]

        # Calculate inflows vs outflows
        inflow = db.query(func.sum(Operation.amount)).filter(
            Operation.company_id == company_id,
            Operation.counterparty_inn == inn,
            Operation.direction == "Поступление"
        ).scalar() or 0.0

        outflow = db.query(func.sum(Operation.amount)).filter(
            Operation.company_id == company_id,
            Operation.counterparty_inn == inn,
            Operation.direction == "Списание"
        ).scalar() or 0.0

        if inflow > 0 and outflow > 0:
            role = "both"
        elif inflow > 0:
            role = "payer"
        else:
            role = "supplier"

        cp = Counterparty(
            company_id=company_id,
            inn=inn,
            name=name,
            role=role,
            turnover=turnover,
            inflow_sum=float(inflow),
            outflow_sum=float(outflow),
            ops_count=ops_cnt,
            last_op_date=last_dt,
            include_in_forecast=True
        )
        db.add(cp)

    db.commit()


@router.get("/companies/{company_id}/counterparties", response_model=List[CounterpartyOut])
def get_company_counterparties(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    _ensure_company_counterparties(company_id, db)
    counterparties = db.query(Counterparty).filter(
        Counterparty.company_id == company_id
    ).order_by(desc(Counterparty.turnover)).all()

    return counterparties


@router.post("/companies/{company_id}/counterparties/{inn}/check", response_model=CounterpartyOut)
def check_counterparty_fns(
    company_id: str,
    inn: str,
    body: Optional[CounterpartyCheckRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Выполняет анализ контрагента по методам nalogbi (блокировки счетов) и check (факторы риска) из api-fns.ru
    """
    cp = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.inn == inn
    ).first()

    if not cp:
        # Create on the fly if not exists
        cp = Counterparty(
            company_id=company_id,
            inn=inn,
            name=f"Контрагент {inn}",
            role="payer",
            include_in_forecast=True
        )
        db.add(cp)

    api_key = body.api_key if body and body.api_key else settings.FNS_API_KEY
    analysis = fns_adapter.analyze_counterparty(inn=inn, name=cp.name, api_key=api_key)

    # Если в ЕГРЮЛ подтверждено официальное наименование — обновляем запись в БД и операции
    if analysis.get("official_name") and "не существует" not in analysis["official_name"].lower():
        cp.name = analysis["official_name"]
        db.query(Operation).filter(
            Operation.company_id == company_id,
            Operation.counterparty_inn == inn
        ).update({Operation.counterparty_name: cp.name}, synchronize_session=False)

    cp.has_blocks = analysis["has_blocks"]
    cp.blocks_count = analysis["blocks_count"]
    cp.blocks_info = analysis["blocks_info"]
    cp.risk_level = analysis["risk_level"]
    cp.reliability_score = analysis["reliability_score"]
    cp.negative_factors = analysis["negative_factors"]
    cp.positive_factors = analysis["positive_factors"]
    cp.check_summary = analysis["check_summary"]
    cp.recommended_action = analysis["recommended_action"]
    cp.last_checked_at = datetime.utcnow()

    db.commit()
    db.refresh(cp)
    return cp


@router.post("/companies/{company_id}/counterparties/check-all", response_model=List[CounterpartyOut])
def check_all_counterparties(
    company_id: str,
    body: Optional[FnsApiKeyRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Пакетная проверка всех контрагентов компании по nalogbi и check
    """
    _ensure_company_counterparties(company_id, db)
    cps = db.query(Counterparty).filter(Counterparty.company_id == company_id).all()
    api_key = body.api_key if body and body.api_key else settings.FNS_API_KEY

    for cp in cps:
        analysis = fns_adapter.analyze_counterparty(inn=cp.inn, name=cp.name, api_key=api_key)
        if analysis.get("official_name") and "не существует" not in analysis["official_name"].lower():
            cp.name = analysis["official_name"]
            db.query(Operation).filter(
                Operation.company_id == company_id,
                Operation.counterparty_inn == cp.inn
            ).update({Operation.counterparty_name: cp.name}, synchronize_session=False)

        cp.has_blocks = analysis["has_blocks"]
        cp.blocks_count = analysis["blocks_count"]
        cp.blocks_info = analysis["blocks_info"]
        cp.risk_level = analysis["risk_level"]
        cp.reliability_score = analysis["reliability_score"]
        cp.negative_factors = analysis["negative_factors"]
        cp.positive_factors = analysis["positive_factors"]
        cp.check_summary = analysis["check_summary"]
        cp.recommended_action = analysis["recommended_action"]
        cp.last_checked_at = datetime.utcnow()

    db.commit()
    return cps


@router.post("/companies/{company_id}/counterparties", response_model=CounterpartyOut)
def create_and_check_counterparty(
    company_id: str,
    req: CounterpartyCreateRequest,
    db: Session = Depends(get_db)
):
    """Добавляет нового контрагента и сразу проверяет его по ФНС"""
    clean_inn = req.inn.strip()
    existing = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.inn == clean_inn
    ).first()

    name = req.name or f"ООО «Партнер-{clean_inn[-4:]}»"
    if not existing:
        existing = Counterparty(
            company_id=company_id,
            inn=clean_inn,
            name=name,
            role=req.role,
            include_in_forecast=req.include_in_forecast
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

    # Perform analysis
    api_key = req.api_key or settings.FNS_API_KEY
    analysis = fns_adapter.analyze_counterparty(inn=clean_inn, name=existing.name, api_key=api_key)
    if analysis.get("official_name") and "не существует" not in analysis["official_name"].lower():
        existing.name = analysis["official_name"]
        db.query(Operation).filter(
            Operation.company_id == company_id,
            Operation.counterparty_inn == clean_inn
        ).update({Operation.counterparty_name: existing.name}, synchronize_session=False)

    existing.has_blocks = analysis["has_blocks"]
    existing.blocks_count = analysis["blocks_count"]
    existing.blocks_info = analysis["blocks_info"]
    existing.risk_level = analysis["risk_level"]
    existing.reliability_score = analysis["reliability_score"]
    existing.negative_factors = analysis["negative_factors"]
    existing.positive_factors = analysis["positive_factors"]
    existing.check_summary = analysis["check_summary"]
    existing.recommended_action = analysis["recommended_action"]
    existing.last_checked_at = datetime.utcnow()

    db.commit()
    db.refresh(existing)
    return existing


@router.patch("/companies/{company_id}/counterparties/{inn}/toggle-forecast")
def toggle_counterparty_forecast(
    company_id: str,
    inn: str,
    body: CounterpartyToggleForecastRequest,
    db: Session = Depends(get_db)
):
    """Переключает галочку 'Учитывать проверку в итоговом графике'"""
    cp = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.inn == inn
    ).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    cp.include_in_forecast = body.include_in_forecast
    db.commit()
    return {"inn": inn, "include_in_forecast": cp.include_in_forecast}


@router.post("/companies/{company_id}/counterparties/api-key")
def save_fns_api_key(company_id: str, body: FnsApiKeyRequest):
    """Сохраняет API ключ api-fns.ru в конфигурации рантайма, файле fns_key.txt и .env"""
    import re
    clean_key = body.api_key.strip() if body and body.api_key else ""
    settings.FNS_API_KEY = clean_key
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # Persist to fns_key.txt
    fns_file = os.path.join(root_dir, "fns_key.txt")
    try:
        with open(fns_file, "w", encoding="utf-8") as f:
            f.write(clean_key)
    except Exception:
        pass

    # Persist to .env
    env_file = os.path.join(root_dir, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
            if re.search(r"^FNS_API_KEY=.*$", content, flags=re.MULTILINE):
                new_content = re.sub(r"^FNS_API_KEY=.*$", f"FNS_API_KEY={clean_key}", content, flags=re.MULTILINE)
            else:
                new_content = content + f"\nFNS_API_KEY={clean_key}\n"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception:
            pass

    return {
        "status": "ok",
        "has_key": bool(clean_key),
        "mode": "live" if clean_key else "demo",
        "message": "Реальный API-ключ api-fns.ru успешно сохранен в .env! Запросы отправляются на https://api-fns.ru/api" if clean_key else "Ключ сброшен (демо-режим)"
    }


@router.get("/companies/{company_id}/counterparties/api-key-status")
def get_fns_api_key_status(company_id: str):
    """Возвращает статус подключения к реальному сайту api-fns.ru"""
    key = settings.FNS_API_KEY or ""
    has_key = bool(key)
    masked = ""
    if has_key:
        masked = key[:4] + "••••" + key[-4:] if len(key) > 8 else "••••••••"
    return {
        "has_key": has_key,
        "masked_key": masked,
        "mode": "live" if has_key else "demo",
        "endpoint": "https://api-fns.ru/api"
    }

