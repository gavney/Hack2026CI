from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
import uuid

from backend.database import get_db
from backend.models import Event, Slot, Company, Operation, Counterparty
from backend.schemas import EventOut, EventCreate, EventUpdate, SlotOut, SlotUpdate, SlotCreate
from backend.core.tax_calendar import sync_tax_calendar_events

router = APIRouter(tags=["События и Регулярные платежи"])

def validate_counterparty_data(inn: Optional[str], name: Optional[str]):
    clean_inn = str(inn or "").strip()
    clean_name = str(name or "").strip()
    if not clean_name or len(clean_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Наименование контрагента обязательно для заполнения (не менее 2 символов)"
        )
    if not clean_inn or not clean_inn.isdigit() or len(clean_inn) not in (10, 12):
        raise HTTPException(
            status_code=400,
            detail="ИНН контрагента обязателен и должен состоять ровно из 10 (для ООО/АО) или 12 (для ИП/Самозанятых) цифр"
        )
    return clean_inn, clean_name

@router.get("/companies/{company_id}/events", response_model=List[EventOut])
def list_events(company_id: str, db: Session = Depends(get_db)):
    try:
        sync_tax_calendar_events(company_id, db)
    except Exception as e:
        print(f"Warning syncing tax events for {company_id}: {e}")
    return db.query(Event).filter(Event.company_id == company_id).order_by(Event.event_date).all()

@router.post("/companies/{company_id}/events", response_model=EventOut)
def create_event(company_id: str, payload: EventCreate, db: Session = Depends(get_db)):
    """
    Fast manual event addition (FR-10.1):
    «Жду поступление» (+) или «Заплачу» (-), сумма, дата, уверенность.
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    clean_inn, clean_name = validate_counterparty_data(payload.counterparty_inn, payload.counterparty_name)

    ev = Event(
        id=f"ev_man_{uuid.uuid4().hex[:8]}",
        company_id=company_id,
        event_date=payload.event_date,
        amount=payload.amount,
        probability=payload.probability,
        category_id=payload.category_id or ('cat_revenue_client' if payload.amount > 0 else 'cat_procurement'),
        counterparty_inn=clean_inn,
        counterparty_name=clean_name,
        source="manual",
        status="expected",
        is_active=payload.is_active if payload.is_active is not None else True,
        note=payload.note
    )
    db.add(ev)

    # Register/link counterparty if missing
    existing_cp = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.inn == clean_inn
    ).first()
    if not existing_cp:
        role = "supplier" if payload.amount < 0 else "payer"
        new_cp = Counterparty(
            company_id=company_id,
            inn=clean_inn,
            name=clean_name,
            role=role,
            include_in_forecast=True
        )
        db.add(new_cp)

    db.commit()
    db.refresh(ev)
    return ev

@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: str,
    payload: Optional[EventUpdate] = None,
    status: Optional[str] = None,
    delay_days: Optional[int] = None,
    actual_amount: Optional[float] = None,
    db: Session = Depends(get_db)
):
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    if payload:
        if payload.event_date is not None:
            ev.event_date = payload.event_date
        if payload.amount is not None:
            ev.amount = payload.amount
        if payload.probability is not None:
            ev.probability = payload.probability
        if payload.category_id is not None:
            ev.category_id = payload.category_id
        if payload.counterparty_inn is not None or payload.counterparty_name is not None:
            c_inn = payload.counterparty_inn if payload.counterparty_inn is not None else ev.counterparty_inn
            c_name = payload.counterparty_name if payload.counterparty_name is not None else ev.counterparty_name
            clean_inn, clean_name = validate_counterparty_data(c_inn, c_name)
            ev.counterparty_inn = clean_inn
            ev.counterparty_name = clean_name
        if payload.status is not None:
            ev.status = payload.status
        if payload.is_active is not None:
            ev.is_active = payload.is_active
        if payload.note is not None:
            ev.note = payload.note

    if status is not None:
        ev.status = status
    if delay_days is not None:
        ev.delay_days = delay_days
    if actual_amount is not None:
        ev.actual_amount = actual_amount

    db.commit()
    db.refresh(ev)
    return ev

@router.post("/events/{event_id}/confirm")
def confirm_event(event_id: str, db: Session = Depends(get_db)):
    """
    Подтверждение выполнения запланированного платежа:
    переводит будущее событие в свершившуюся историческую операцию (Operation).
    """
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    comp = db.query(Company).filter(Company.id == ev.company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    direction = "Поступление" if ev.amount > 0 else "Списание"
    abs_amt = abs(ev.amount)
    cur_bal = float(comp.last_balance or 0.0)
    if direction == "Поступление":
        new_bal = cur_bal + abs_amt
    else:
        new_bal = cur_bal - abs_amt

    today_dt = date.today()
    op = Operation(
        company_id=comp.id,
        operation_id=f"conf_{uuid.uuid4().hex[:8]}",
        operation_date=today_dt,
        amount=abs_amt,
        direction=direction,
        counterparty_name=ev.counterparty_name or "Контрагент",
        counterparty_inn=ev.counterparty_inn or "",
        payment_purpose=f"Подтвержденный платеж: {ev.counterparty_name or ''}",
        balance_eod=new_bal,
        category_id=ev.category_id or ("cat_revenue_client" if direction == "Поступление" else "cat_procurement"),
        category_source="manual_confirm",
        category_confidence=1.0
    )
    db.add(op)
    comp.last_balance = new_bal
    comp.operations_count = (comp.operations_count or 0) + 1
    if not comp.first_operation_date or today_dt < comp.first_operation_date:
        comp.first_operation_date = today_dt
    if not comp.last_operation_date or today_dt > comp.last_operation_date:
        comp.last_operation_date = today_dt

    db.delete(ev)
    db.commit()

    try:
        sync_tax_calendar_events(comp.id, db)
    except Exception as e:
        print(f"Warning syncing tax events: {e}")

    return {
        "status": "ok",
        "message": "Платеж успешно подтвержден и перенесен в историю операций",
        "operation_id": op.id,
        "new_balance": new_bal
    }

@router.delete("/events/{event_id}")
def delete_event(event_id: str, db: Session = Depends(get_db)):
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    db.delete(ev)
    db.commit()
    return {"status": "ok", "message": "Запланированный платеж удален"}

# --- Slots Management (FR-3.1, FR-3.5) ---
@router.get("/companies/{company_id}/slots", response_model=List[SlotOut])
def list_slots(company_id: str, db: Session = Depends(get_db)):
    return db.query(Slot).filter(Slot.company_id == company_id).order_by(Slot.day_of_month).all()

@router.patch("/slots/{slot_id}", response_model=SlotOut)
def update_slot(slot_id: int, payload: SlotUpdate, db: Session = Depends(get_db)):
    slot = db.query(Slot).filter(Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Слот не найден")

    if payload.typical_amount is not None:
        slot.typical_amount = payload.typical_amount
    if payload.day_of_month is not None:
        slot.day_of_month = payload.day_of_month
    if payload.confirmed_by_user is not None:
        slot.confirmed_by_user = payload.confirmed_by_user
    if payload.is_active is not None:
        slot.is_active = payload.is_active

    db.commit()
    db.refresh(slot)
    return slot

@router.post("/companies/{company_id}/slots", response_model=SlotOut)
def create_slot(company_id: str, payload: SlotCreate, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    new_slot = Slot(
        company_id=company_id,
        category_id=payload.category_id or ('cat_revenue_client' if payload.amount > 0 else 'cat_procurement'),
        direction=payload.direction,
        day_of_month=payload.day_of_month,
        typical_amount=payload.typical_amount,
        counterparty_name=payload.counterparty_name or "Регулярный платеж",
        counterparty_inn=payload.counterparty_inn or "",
        share_of_months=1.0,
        confirmed_by_user=True,
        is_active=True
    )
    db.add(new_slot)
    db.commit()
    db.refresh(new_slot)
    return new_slot

@router.delete("/slots/{slot_id}")
def delete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(Slot).filter(Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Слот не найден")
    db.delete(slot)
    db.commit()
    return {"status": "ok", "message": "Слот удален"}
