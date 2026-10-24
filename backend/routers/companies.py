from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import io
import os
import time
import uuid
import sqlite3
import threading
import pandas as pd

from backend.database import get_db
from backend.models import Company, Operation, Slot, UserCompany, User, Scenario, IntegrationSource, StatementUploadHistory
from backend.schemas import (
    CompanyOut,
    CompanyCreate,
    CompanyUpdate,
    QualityReportOut,
    StatementUploadResult,
    StatementUploadTaskResponse,
    StatementProgressResponse,
    StatementUploadHistoryOut
)
from backend.routers.auth import get_current_user_optional, get_current_user_required
from backend.routers.scenarios import DEFAULT_SCENARIOS
from backend.routers.integrations import DEFAULT_INTEGRATION_CONFIGS
from backend.core.cleaning import parse_operations_csv
from backend.core.statement_parsers import parse_any_statement, InvoiceParser, ContractParser
from backend.core.categorizer import classify_operation
from backend.core.slots import detect_recurring_slots, infer_tax_regime

router = APIRouter(prefix="/companies", tags=["Компании и Загрузка выписок"])

# In-memory storage for active statement processing tasks
STATEMENT_TASKS: Dict[str, Dict[str, Any]] = {}

def check_company_access(company_id: str, authorization: Optional[str], db: Session):
    """
    Разграничение прав:
    - C001 и C004 — публичные демонстрационные компании (для демо и автотестов).
    - Для остальных бизнесов доступ без авторизации СТРОГО ЗАПРЕЩЕН (401).
    - Авторизованный пользователь видит только те бизнесы, которые привязаны к его аккаунту (403),
      либо если его роль bank_manager (супервайзер банка «Центр-инвест»).
    """
    if company_id in ["C001", "C004"]:
        return
    user = get_current_user_optional(authorization, db)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Доступ к данным компании ограничен. Авторизуйтесь под своей учетной записью."
        )
    if user.role == "bank_manager":
        return
    ucs = db.query(UserCompany).filter(
        UserCompany.user_id == user.id,
        UserCompany.company_id == company_id
    ).first()
    if not ucs and user.company_id != company_id:
        raise HTTPException(
            status_code=403,
            detail="У вас нет прав доступа к этой компании. Доступ разрешен только владельцу бизнеса."
        )

@router.get("", response_model=List[CompanyOut])
def list_companies(
    authorization: Optional[str] = Header(None),
    industry: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 150,
    db: Session = Depends(get_db)
):
    """
    Разграничение прав доступа к списку бизнесов:
    - Без авторизации: доступен ТОЛЬКО демо-бизнес C001 (ООО «Агро-063»).
      Чужие 149 бизнесов скрыты и недоступны.
    - Авторизованный аккаунт: видит ИСКЛЮЧИТЕЛЬНО свои привязанные бизнесы.
    - Банковский менеджер (bank_manager): видит все компании для скоринга.
    """
    user = get_current_user_optional(authorization, db)

    # 1. Гостевой режим (без авторизации) -> пустые данные (требуется вход)
    if not user:
        return []

    # 2. Сотрудник банка Центр-инвест -> полный реестр компаний
    if user.role == "bank_manager":
        query = db.query(Company)
        if industry:
            query = query.filter(Company.industry == industry)
        if search:
            query = query.filter(
                (Company.name.ilike(f"%{search}%")) |
                (Company.inn.ilike(f"%{search}%")) |
                (Company.id.ilike(f"%{search}%"))
            )
        return query.order_by(Company.id).limit(limit).all()

    # 3. Авторизованный предприниматель -> ТОЛЬКО свои бизнесы из user_companies
    ucs = db.query(UserCompany).filter(UserCompany.user_id == user.id).all()
    user_company_ids = [uc.company_id for uc in ucs]
    if user.company_id and user.company_id not in user_company_ids:
        user_company_ids.append(user.company_id)
        # Сохраняем в связующую таблицу
        uc = UserCompany(user_id=user.id, company_id=user.company_id, role="owner", is_default=True)
        db.add(uc)
        db.commit()

    if not user_company_ids:
        return []

    query = db.query(Company).filter(Company.id.in_(user_company_ids))
    if search:
        query = query.filter((Company.name.ilike(f"%{search}%")) | (Company.inn.ilike(f"%{search}%")))
    return query.order_by(Company.name).all()

def validate_inn_and_fields(inn: str, legal_form: str, name: str):
    clean_inn = str(inn).strip()
    if not clean_inn or not clean_inn.isdigit():
        raise HTTPException(status_code=400, detail="ИНН должен состоять только из цифр")
    if legal_form in ["ООО", "АО"] and len(clean_inn) != 10:
        raise HTTPException(status_code=400, detail="ИНН юридического лица (ООО, АО) должен содержать ровно 10 цифр")
    if legal_form in ["ИП", "Самозанятый"] and len(clean_inn) != 12:
        raise HTTPException(status_code=400, detail="ИНН индивидуального предпринимателя или самозанятого должен содержать ровно 12 цифр")
    if len(name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Название компании должно содержать минимум 2 символа")

@router.post("", response_model=CompanyOut)
def create_company(
    payload: CompanyCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Добавление нового бизнеса под текущий аккаунт:
    - Создает компанию в БД
    - Привязывает ее к текущему пользователю в user_companies (роль owner)
    - Инициализирует интеграционные слоты и стресс-сценарии
    - Устанавливает ее как текущую активную компанию
    """
    user = get_current_user_required(authorization, db)
    validate_inn_and_fields(payload.inn, payload.legal_form or "ООО", payload.name)

    company_id = f"U_{uuid.uuid4().hex[:6].upper()}"

    comp = Company(
        id=company_id,
        name=payload.name.strip(),
        inn=str(payload.inn).strip(),
        legal_form=payload.legal_form or "ООО",
        industry=payload.industry or "Оптовая торговля",
        overdraft_limit=float(payload.overdraft_limit or 0.0),
        tax_regime=payload.tax_regime or "УСН Доходы 6%",
        tax_regime_confirmed=True,
        has_statement=False,  # Новый бизнес до загрузки первой выписки
        initial_manual_balance=float(payload.initial_balance or 0.0),
        last_balance=float(payload.initial_balance or 0.0),
        created_by_user_id=user.id,
        operations_count=0,
        data_quality_score=100.0
    )
    db.add(comp)

    # Привязка компании к текущему аккаунту в связующей таблице
    uc = UserCompany(
        user_id=user.id,
        company_id=company_id,
        role="owner",
        is_default=False
    )
    db.add(uc)

    # Устанавливаем активную компанию пользователя
    user.company_id = company_id

    # Инициализация интеграций и 4 сценариев для новой компании
    for dic in DEFAULT_INTEGRATION_CONFIGS:
        src = IntegrationSource(
            company_id=company_id,
            adapter_name=dic["adapter_name"],
            display_name=dic["display_name"],
            description=dic["description"],
            status=dic["status"],
            events_added=0,
            last_sync_at=datetime.utcnow()
        )
        db.add(src)

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
    db.refresh(comp)

    if payload.tax_regime is not None:
        try:
            from backend.core.tax_calendar import sync_tax_calendar_events
            sync_tax_calendar_events(company_id, db)
        except Exception as e:
            print(f"Error syncing tax calendar: {e}")

    return comp

@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    check_company_access(company_id, authorization, db)
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    return comp

@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: str,
    payload: CompanyUpdate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    check_company_access(company_id, authorization, db)
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    if payload.name is not None:
        comp.name = payload.name
    if payload.legal_form is not None:
        comp.legal_form = payload.legal_form
    if payload.industry is not None:
        comp.industry = payload.industry
    if payload.overdraft_limit is not None:
        comp.overdraft_limit = payload.overdraft_limit
    if payload.tax_regime is not None:
        comp.tax_regime = payload.tax_regime
    if payload.tax_regime_confirmed is not None:
        comp.tax_regime_confirmed = payload.tax_regime_confirmed
    if payload.initial_manual_balance is not None:
        comp.initial_manual_balance = payload.initial_manual_balance
        if payload.initial_manual_balance == 0:
            # Сброс к остатку по файлу на последний расчетный день
            last_op = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date.desc(), Operation.id.desc()).first()
            if last_op:
                comp.last_balance = float(last_op.balance_eod)
            else:
                comp.last_balance = 0.0
        else:
            comp.last_balance = payload.initial_manual_balance

    if payload.last_balance is not None:
        comp.last_balance = payload.last_balance
        comp.initial_manual_balance = payload.last_balance

    db.commit()
    db.refresh(comp)

    if payload.tax_regime is not None:
        try:
            from backend.core.tax_calendar import sync_tax_calendar_events
            sync_tax_calendar_events(company_id, db)
        except Exception as e:
            print(f"Error syncing tax calendar: {e}")

    return comp

@router.get("/{company_id}/quality", response_model=QualityReportOut)
def get_quality_report(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    stmt_path = os.path.join("data", "statements", f"{company_id}.csv")
    if os.path.exists(stmt_path):
        _, qr = parse_operations_csv(stmt_path)
    else:
        qr = {
            "initial_count": comp.operations_count,
            "clean_count": comp.operations_count,
            "duplicate_rows_count": 0,
            "missing_inn_count": 0,
            "missing_purpose_count": 0,
            "gaps_longer_than_7_days": [],
            "balance_jumps_count": 0,
            "negative_balance_days_count": 0,
            "quality_score": comp.data_quality_score or 95.0,
            "warnings": []
        }

    return QualityReportOut(
        company_id=comp.id,
        quality_score=qr["quality_score"],
        total_operations=qr["clean_count"],
        date_range=f"{qr.get('first_date', comp.first_operation_date or '—')} — {qr.get('last_date', comp.last_operation_date or '—')}",
        duplicate_rows_count=qr["duplicate_rows_count"],
        missing_inn_count=qr["missing_inn_count"],
        missing_purpose_count=qr["missing_purpose_count"],
        gaps_longer_than_7_days=qr["gaps_longer_than_7_days"],
        balance_jumps_count=qr["balance_jumps_count"],
        negative_balance_days_count=qr["negative_balance_days_count"],
        warnings=qr["warnings"]
    )

def execute_statement_pipeline(
    company_id: str,
    content_bytes: bytes,
    filename: str = "statement.csv",
    task_id: Optional[str] = None
) -> StatementUploadResult:
    start_time = time.time()
    file_size_mb = round(len(content_bytes) / (1024 * 1024), 2)

    def update_task(stage: str, stage_text: str, progress_pct: int, **kwargs):
        if not task_id or task_id not in STATEMENT_TASKS:
            return
        elapsed = round(time.time() - start_time, 1)
        data = {
            "task_id": task_id,
            "status": "processing",
            "stage": stage,
            "stage_text": stage_text,
            "progress_pct": progress_pct,
            "filename": filename,
            "file_size_mb": file_size_mb,
            "elapsed_seconds": elapsed,
        }
        data.update(kwargs)
        STATEMENT_TASKS[task_id].update(data)

    update_task("parsing", "Определение формата (Сбербанк PDF, 1C TXT, CSV, Excel)...", 10)

    from backend.database import SessionLocal

    # Get company INN and initial balance if available
    comp_inn = None
    comp_bal = 0.0
    try:
        tmp_db = SessionLocal()
        c_obj = tmp_db.query(Company).filter(Company.id == company_id).first()
        if c_obj:
            comp_inn = c_obj.inn
            comp_bal = c_obj.last_balance or 0.0
        tmp_db.close()
    except Exception:
        pass

    update_task("parsing", "Разбор транзакций, анонимизация ПДн и извлечение НДС...", 20)
    clean_df, qr = parse_any_statement(
        content_bytes=content_bytes,
        filename=filename,
        company_inn=comp_inn,
        initial_balance=comp_bal
    )

    if clean_df.empty:
        raise ValueError(f"Файл выписки '{filename}' не содержит распознанных операций.")

    total_rows = len(clean_df)
    update_task("cleaning", f"Проверено {total_rows:,} операций. Дедупликация и валидация ИНН...", 30, total_rows=total_rows)

    # 2. Fast vectorized categorization
    directions = clean_df['direction'].astype(str).tolist()
    purposes = clean_df['payment_purpose'].fillna('').astype(str).tolist()
    inns = clean_df['counterparty_inn'].fillna('').astype(str).tolist()
    names = clean_df['counterparty_name'].fillna('').astype(str).tolist()

    cat_ids = []
    confidences = []
    sources = []

    batch_update_size = max(2000, total_rows // 25)
    cat_start = time.time()

    for idx in range(total_rows):
        c_id, conf, src = classify_operation(
            direction=directions[idx],
            payment_purpose=purposes[idx],
            counterparty_inn=inns[idx],
            counterparty_name=names[idx]
        )
        cat_ids.append(c_id)
        confidences.append(conf)
        sources.append(src)

        if (idx + 1) % batch_update_size == 0 or idx == total_rows - 1:
            now = time.time()
            cat_elapsed = max(0.01, now - cat_start)
            speed = round((idx + 1) / cat_elapsed, 0)
            remaining = total_rows - (idx + 1)
            eta = round(remaining / max(1.0, speed), 1)
            pct = 30 + int(((idx + 1) / total_rows) * 45)

            update_task(
                "categorizing",
                f"Интеллектуальная разметка категорий: {idx + 1:,} из {total_rows:,} операций...",
                min(75, pct),
                processed_rows=idx + 1,
                total_rows=total_rows,
                speed_rows_per_sec=speed,
                eta_seconds=eta
            )

    clean_df['category_id'] = cat_ids

    # 3. High-speed direct SQLite bulk insertion
    update_task("saving", "Пакетная запись операций в базу данных radar.db...", 80, processed_rows=total_rows, total_rows=total_rows)

    conn = sqlite3.connect("radar.db", timeout=60.0)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM operations WHERE company_id = ?", (company_id,))
    cursor.execute("DELETE FROM slots WHERE company_id = ?", (company_id,))
    conn.commit()

    dates = [d.date().isoformat() if hasattr(d, 'date') else str(d)[:10] for d in clean_df['operation_date']]
    amounts = clean_df['amount'].astype(float).tolist()
    eods = clean_df['balance_eod'].astype(float).tolist()
    op_ids = [str(clean_df.iloc[i].get('operation_id', f'op_{i}')) for i in range(total_rows)]
    is_dups = [bool(clean_df.iloc[i].get('is_duplicate', False)) for i in range(total_rows)]

    insert_rows = []
    db_batch_size = 25000
    for i in range(total_rows):
        insert_rows.append((
            company_id,
            op_ids[i],
            dates[i],
            amounts[i],
            directions[i],
            inns[i],
            names[i],
            purposes[i],
            eods[i],
            cat_ids[i],
            confidences[i],
            sources[i],
            is_dups[i]
        ))
        if len(insert_rows) >= db_batch_size:
            cursor.executemany("""
                INSERT INTO operations (
                    company_id, operation_id, operation_date, amount, direction,
                    counterparty_inn, counterparty_name, payment_purpose, balance_eod,
                    category_id, category_confidence, category_source, is_duplicate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, insert_rows)
            conn.commit()
            insert_rows = []

    if insert_rows:
        cursor.executemany("""
            INSERT INTO operations (
                company_id, operation_id, operation_date, amount, direction,
                counterparty_inn, counterparty_name, payment_purpose, balance_eod,
                category_id, category_confidence, category_source, is_duplicate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_rows)
        conn.commit()

    # 4. Recurring slots detection
    update_task("slots", "Выявление регулярных платежей (аренда, налоги, зарплата)...", 90)

    slots = detect_recurring_slots(clean_df)
    slot_rows = []
    for s in slots:
        slot_rows.append((
            company_id,
            s["category_id"],
            s["counterparty_inn"],
            s["counterparty_name"],
            s["direction"],
            s["day_of_month"],
            s["typical_amount"],
            s["share_of_months"],
            1,
            1
        ))

    if slot_rows:
        cursor.executemany("""
            INSERT INTO slots (
                company_id, category_id, counterparty_inn, counterparty_name,
                direction, day_of_month, typical_amount, share_of_months,
                confirmed_by_user, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, slot_rows)
        conn.commit()

    # 5. Metadata update
    min_date = clean_df['operation_date'].min()
    max_date = clean_df['operation_date'].max()
    min_date_str = min_date.strftime('%Y-%m-%d') if hasattr(min_date, 'strftime') else str(min_date)[:10]
    max_date_str = max_date.strftime('%Y-%m-%d') if hasattr(max_date, 'strftime') else str(max_date)[:10]
    last_bal = float(clean_df.iloc[-1]['balance_eod'])
    regime, _ = infer_tax_regime(clean_df)

    cursor.execute("""
        UPDATE companies
        SET has_statement = 1,
            operations_count = ?,
            last_balance = ?,
            first_operation_date = ?,
            last_operation_date = ?,
            data_quality_score = ?,
            tax_regime = COALESCE(tax_regime, ?)
        WHERE id = ?
    """, (total_rows, last_bal, min_date_str, max_date_str, qr["quality_score"], regime, company_id))
    conn.commit()
    conn.close()

    total_time = round(time.time() - start_time, 2)

    # Log statement upload to history
    try:
        from backend.database import SessionLocal
        hist_db = SessionLocal()
        hist = StatementUploadHistory(
            id=f"up_{uuid.uuid4().hex[:10]}",
            company_id=company_id,
            filename=filename,
            file_size_bytes=len(content_bytes),
            uploaded_at=datetime.utcnow(),
            status="success",
            operations_count=total_rows,
            slots_detected=len(slots),
            last_balance=last_bal,
            data_quality_score=qr.get("quality_score", 100.0),
            execution_time_sec=total_time
        )
        hist_db.add(hist)
        hist_db.commit()
        hist_db.close()
    except Exception as e:
        print(f"Error logging statement upload history: {e}")

    try:
        from backend.database import SessionLocal
        from backend.core.tax_calendar import sync_tax_calendar_events
        t_db = SessionLocal()
        sync_tax_calendar_events(company_id, t_db)
        t_db.close()
    except Exception as e:
        print(f"Error syncing tax calendar on upload: {e}")

    result = StatementUploadResult(
        status="success",
        message=f"Выписка успешно загружена за {total_time} сек: обработано {total_rows:,} операций, обнаружено {len(slots)} регулярных слотов.",
        operations_count=total_rows,
        first_date=min_date_str,
        last_date=max_date_str,
        last_balance=last_bal,
        quality_score=qr["quality_score"],
        slots_count=len(slots),
        has_statement=True,
        warnings=qr.get("warnings", [])
    )

    if task_id and task_id in STATEMENT_TASKS:
        STATEMENT_TASKS[task_id].update({
            "status": "completed",
            "stage": "done",
            "stage_text": "Готово! Выписка и регулярные слоты успешно проанализированы.",
            "progress_pct": 100,
            "processed_rows": total_rows,
            "total_rows": total_rows,
            "elapsed_seconds": total_time,
            "eta_seconds": 0.0,
            "result": result.model_dump()
        })

    return result


def _async_worker_wrapper(task_id: str, company_id: str, content_bytes: bytes, filename: str):
    try:
        execute_statement_pipeline(company_id, content_bytes, filename, task_id=task_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        if task_id in STATEMENT_TASKS:
            STATEMENT_TASKS[task_id].update({
                "status": "error",
                "stage": "error",
                "stage_text": f"Ошибка: {str(e)}",
                "progress_pct": 0,
                "error": str(e)
            })


@router.post("/{company_id}/upload-statement-async", response_model=StatementUploadTaskResponse)
async def upload_company_statement_async(
    company_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Асинхронная загрузка банковской выписки с поддержкой прогресс-бара в реальном времени.
    Возвращает task_id для отслеживания прогресса (чтение, категоризация, запись, слоты).
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Файл выписки пуст")

    task_id = str(uuid.uuid4())
    file_size_mb = round(len(content_bytes) / (1024 * 1024), 2)

    STATEMENT_TASKS[task_id] = {
        "task_id": task_id,
        "status": "processing",
        "stage": "started",
        "stage_text": "Файл получен сервером, запуск конвейера обработки...",
        "progress_pct": 5,
        "filename": file.filename or "statement.csv",
        "file_size_mb": file_size_mb,
        "processed_rows": 0,
        "total_rows": 0,
        "speed_rows_per_sec": 0.0,
        "elapsed_seconds": 0.0,
        "eta_seconds": 0.0,
        "result": None,
        "error": None
    }

    t = threading.Thread(
        target=_async_worker_wrapper,
        args=(task_id, company_id, content_bytes, file.filename or "statement.csv"),
        daemon=True
    )
    t.start()

    return StatementUploadTaskResponse(
        task_id=task_id,
        status="started",
        message="Файл принят сервером, начата фоновая обработка"
    )


@router.get("/{company_id}/upload-progress/{task_id}", response_model=StatementProgressResponse)
def get_upload_progress(company_id: str, task_id: str):
    """
    Получение текущего прогресса обработки выписки в реальном времени.
    """
    task = STATEMENT_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача обработки выписки не найдена")
    return task


@router.post("/{company_id}/upload-statement", response_model=StatementUploadResult)
async def upload_company_statement(
    company_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Синхронная загрузка банковской выписки (для обратной совместимости) с оптимизированным конвейером.
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    content_bytes = await file.read()
    try:
        return execute_statement_pipeline(company_id, content_bytes, file.filename or "statement.csv")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки выписки: {str(e)}")

@router.post("/{company_id}/load-demo-statement", response_model=StatementUploadResult)
def load_demo_statement(
    company_id: str,
    demo_sample: str = Query("C001", description="Код демонстрационной выписки: C001 (стабильный) или C004 (с разрывом)"),
    db: Session = Depends(get_db)
):
    """
    Быстрая загрузка демо-выписки кейса для тестирования нового бизнеса в 1 клик
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    sample_path = os.path.join("data", "statements", f"{demo_sample}.csv")
    if not os.path.exists(sample_path):
        sample_path = os.path.join("data", "statements", "C001.csv")

    clean_df, qr = parse_operations_csv(sample_path)

    # Clear old operations
    db.query(Operation).filter(Operation.company_id == company_id).delete()
    db.query(Slot).filter(Slot.company_id == company_id).delete()

    cat_list = []
    for _, r in clean_df.iterrows():
        cat_id, conf, src = classify_operation(
            direction=r['direction'],
            payment_purpose=r['payment_purpose'],
            counterparty_inn=r['counterparty_inn'],
            counterparty_name=r['counterparty_name']
        )
        cat_list.append((cat_id, conf, src))

    clean_df['category_id'] = [c[0] for c in cat_list]

    db_ops = []
    for idx, r in clean_df.iterrows():
        cat_id, conf, src = cat_list[idx]
        db_ops.append(Operation(
            company_id=company_id,
            operation_id=str(r.get('operation_id', f'op_{idx}')),
            operation_date=r['operation_date'].date(),
            amount=float(r['amount']),
            direction=str(r['direction']),
            counterparty_inn=str(r['counterparty_inn']) if r['counterparty_inn'] else "",
            counterparty_name=str(r['counterparty_name']),
            payment_purpose=str(r['payment_purpose']),
            balance_eod=float(r['balance_eod']),
            category_id=cat_id,
            category_confidence=conf,
            category_source=src,
            is_duplicate=bool(r.get('is_duplicate', False))
        ))
    db.bulk_save_objects(db_ops)

    slots = detect_recurring_slots(clean_df)
    for s in slots:
        db.add(Slot(
            company_id=company_id,
            category_id=s["category_id"],
            counterparty_inn=s["counterparty_inn"],
            counterparty_name=s["counterparty_name"],
            direction=s["direction"],
            day_of_month=s["day_of_month"],
            typical_amount=s["typical_amount"],
            share_of_months=s["share_of_months"],
            confirmed_by_user=True,
            is_active=True
        ))

    comp.has_statement = True
    comp.operations_count = len(clean_df)
    comp.last_balance = float(clean_df.iloc[-1]['balance_eod'])
    comp.first_operation_date = clean_df['operation_date'].min().date()
    comp.last_operation_date = clean_df['operation_date'].max().date()
    comp.data_quality_score = qr["quality_score"]

    # Log demo statement upload
    try:
        hist = StatementUploadHistory(
            id=f"up_{uuid.uuid4().hex[:10]}",
            company_id=company_id,
            filename=f"Демо-выписка ({demo_sample}).csv",
            file_size_bytes=os.path.getsize(sample_path) if os.path.exists(sample_path) else 1024,
            uploaded_at=datetime.utcnow(),
            status="success",
            operations_count=len(clean_df),
            slots_detected=len(slots),
            last_balance=comp.last_balance,
            data_quality_score=qr.get("quality_score", 100.0),
            execution_time_sec=0.1
        )
        db.add(hist)
    except Exception as e:
        print(f"Error logging demo upload: {e}")

    db.commit()
    db.refresh(comp)

    try:
        from backend.core.tax_calendar import sync_tax_calendar_events
        sync_tax_calendar_events(company_id, db)
    except Exception as e:
        print(f"Error syncing tax calendar on demo load: {e}")

    return StatementUploadResult(
        status="success",
        message=f"Демо-выписка ({demo_sample}) успешно подгружена: {len(clean_df)} операций, {len(slots)} слотов.",
        operations_count=len(clean_df),
        first_date=clean_df['operation_date'].min().strftime('%Y-%m-%d'),
        last_date=clean_df['operation_date'].max().strftime('%Y-%m-%d'),
        last_balance=comp.last_balance,
        quality_score=qr["quality_score"],
        slots_count=len(slots),
        has_statement=True
    )

@router.get("/{company_id}/uploads", response_model=List[StatementUploadHistoryOut])
def get_statement_upload_history(company_id: str, db: Session = Depends(get_db)):
    """
    Возвращает историю загрузок выписок (CSV) для бизнеса.
    """
    return db.query(StatementUploadHistory).filter(
        StatementUploadHistory.company_id == company_id
    ).order_by(StatementUploadHistory.uploaded_at.desc()).limit(25).all()

@router.delete("/{company_id}")
def delete_company(
    company_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Удаление бизнеса (доступно владельцу бизнеса или менеджеру банка).
    """
    user = get_current_user_required(authorization, db)
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    if user.role != "bank_manager":
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == company_id
        ).first()
        if not uc and user.company_id != company_id:
            raise HTTPException(status_code=403, detail="У вас нет прав на удаление этого бизнеса")

    comp_name = comp.name

    # Delete UserCompany associations
    db.query(UserCompany).filter(UserCompany.company_id == company_id).delete()
    # Delete related statement upload history
    db.query(StatementUploadHistory).filter(StatementUploadHistory.company_id == company_id).delete()

    # Delete company
    db.delete(comp)

    # If this was user's current company, switch to remaining one
    next_id = None
    if user.company_id == company_id:
        remaining = db.query(UserCompany).filter(UserCompany.user_id == user.id).first()
        user.company_id = remaining.company_id if remaining else None
        next_id = user.company_id

    db.commit()
    return {"status": "ok", "message": f"Бизнес «{comp_name}» успешно удален", "next_company_id": next_id}

