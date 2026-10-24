from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
import uuid
from backend.database import get_db
from backend.models import Operation, Category, CategoryMemory, Company, Counterparty
from backend.schemas import (
    OperationOut, OperationCategoryUpdate, OperationCreate,
    CategoryOut, CategoryCreate, CategoryUpdate
)
from backend.core.categorizer import STANDARD_CATEGORIES, normalize_purpose
from backend.core.tax_calendar import sync_tax_calendar_events

router = APIRouter(tags=["Операции и категории"])

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

@router.get("/companies/{company_id}/operations", response_model=List[OperationOut])
def get_operations(
    company_id: str,
    direction: Optional[str] = None,
    category_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Operation).filter(Operation.company_id == company_id)
    if direction:
        query = query.filter(Operation.direction == direction)
    if category_id:
        query = query.filter(Operation.category_id == category_id)
    if date_from:
        query = query.filter(Operation.operation_date >= date_from)
    if date_to:
        query = query.filter(Operation.operation_date <= date_to)

    total_ops = query.order_by(Operation.operation_date.desc(), Operation.id.desc()).offset((page - 1) * limit).limit(limit).all()

    # Enrich with category name
    results = []
    cat_names = {c.id: c.name for c in db.query(Category).all()}
    for op in total_ops:
        out = OperationOut.model_validate(op)
        out.category_name = cat_names.get(op.category_id, "Без категории")
        results.append(out)

    return results

@router.post("/companies/{company_id}/operations", response_model=OperationOut)
def create_manual_operation(
    company_id: str,
    payload: OperationCreate,
    db: Session = Depends(get_db)
):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    clean_inn, clean_name = validate_counterparty_data(payload.counterparty_inn, payload.counterparty_name)

    abs_amt = abs(payload.amount)
    direction = "Поступление" if payload.direction == "Поступление" else "Списание"

    cur_bal = float(comp.last_balance or 0.0)
    if direction == "Поступление":
        new_bal = cur_bal + abs_amt
    else:
        new_bal = cur_bal - abs_amt

    op = Operation(
        company_id=company_id,
        operation_id=f"man_{uuid.uuid4().hex[:8]}",
        operation_date=payload.operation_date,
        amount=abs_amt,
        direction=direction,
        counterparty_inn=clean_inn,
        counterparty_name=clean_name,
        payment_purpose=payload.payment_purpose or f"Оплата: {clean_name}",
        balance_eod=new_bal,
        category_id=payload.category_id,
        category_source="manual",
        category_confidence=1.0
    )
    db.add(op)

    # Register/link counterparty if missing
    existing_cp = db.query(Counterparty).filter(
        Counterparty.company_id == company_id,
        Counterparty.inn == clean_inn
    ).first()
    if not existing_cp:
        role = "supplier" if direction == "Списание" else "payer"
        new_cp = Counterparty(
            company_id=company_id,
            inn=clean_inn,
            name=clean_name,
            role=role,
            include_in_forecast=True
        )
        db.add(new_cp)

    comp.last_balance = new_bal
    comp.operations_count = (comp.operations_count or 0) + 1
    if not comp.first_operation_date or payload.operation_date < comp.first_operation_date:
        comp.first_operation_date = payload.operation_date
    if not comp.last_operation_date or payload.operation_date > comp.last_operation_date:
        comp.last_operation_date = payload.operation_date

    db.commit()
    db.refresh(op)

    try:
        sync_tax_calendar_events(company_id, db)
    except Exception as e:
        print(f"Warning syncing tax events: {e}")

    cat = db.query(Category).filter(Category.id == op.category_id).first()
    out = OperationOut.model_validate(op)
    out.category_name = cat.name if cat else "Без категории"
    return out

@router.patch("/operations/{operation_id}/category", response_model=OperationOut)
def update_operation_category(
    operation_id: int,
    payload: OperationCategoryUpdate,
    db: Session = Depends(get_db)
):
    op = db.query(Operation).filter(Operation.id == operation_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Операция не найдена")

    cat = db.query(Category).filter(Category.id == payload.category_id).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Категория не найдена")

    op.category_id = payload.category_id
    op.category_source = "user"
    op.category_confidence = 1.0

    # Apply to similar operations & save to memory (FR-2.4, FR-2.11)
    if payload.apply_to_similar and op.payment_purpose:
        norm_p = normalize_purpose(op.payment_purpose)
        norm_key = f"{norm_p}||{op.counterparty_inn or ''}"

        # Save/update CategoryMemory
        mem = db.query(CategoryMemory).filter(
            CategoryMemory.company_id == op.company_id,
            CategoryMemory.norm_key == norm_key
        ).first()

        if mem:
            mem.category_id = payload.category_id
            mem.uses_count += 1
        else:
            new_mem = CategoryMemory(
                company_id=op.company_id,
                norm_key=norm_key,
                category_id=payload.category_id,
                uses_count=1
            )
            db.add(new_mem)

        # Update all other operations matching this normalized purpose for the company
        similar_ops = db.query(Operation).filter(
            Operation.company_id == op.company_id,
            Operation.counterparty_inn == op.counterparty_inn,
            Operation.direction == op.direction
        ).all()

        for s_op in similar_ops:
            if normalize_purpose(s_op.payment_purpose) == norm_p:
                s_op.category_id = payload.category_id
                s_op.category_source = "memory"
                s_op.category_confidence = 1.0

    db.commit()
    db.refresh(op)

    try:
        sync_tax_calendar_events(op.company_id, db)
    except Exception as e:
        print(f"Warning syncing tax events: {e}")

    out = OperationOut.model_validate(op)
    out.category_name = cat.name
    return out

@router.get("/companies/{company_id}/categories", response_model=List[CategoryOut])
def list_categories(company_id: str, db: Session = Depends(get_db)):
    # Return standard system categories + custom company categories
    return db.query(Category).filter(
        (Category.company_id == None) | (Category.company_id == company_id)
    ).all()

@router.post("/companies/{company_id}/categories", response_model=CategoryOut)
def create_category(company_id: str, payload: CategoryCreate, db: Session = Depends(get_db)):
    cat = Category(
        id=payload.id,
        company_id=company_id,
        parent_id=payload.parent_id,
        name=payload.name,
        cashflow_role=payload.cashflow_role,
        color=payload.color,
        icon=payload.icon,
        status="confirmed"
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
