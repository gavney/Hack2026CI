from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import io
import csv

from backend.database import get_db
from backend.models import IntegrationSource, Company, Event, Operation
from backend.schemas import IntegrationSourceOut, IntegrationSyncRequest
from backend.core.integrations import ADAPTER_REGISTRY, get_adapter, generate_1c_client_bank_exchange
from backend.core.integrations.adapter_fns import AdapterFNSNalog

router = APIRouter(tags=["Интеграции и Экспорт"])

DEFAULT_INTEGRATION_CONFIGS = [
    {
        "adapter_name": "1c_enterprise",
        "display_name": "1С:Предприятие 8.3 (Счета и Договоры)",
        "description": "Синхронизация неоплаченных счетов покупателям и счетов от поставщиков через OData и обмен 1CClientBankExchange.",
        "status": "mock",
        "events_added": 3
    },
    {
        "adapter_name": "fns_nalog",
        "display_name": "ФНС России (ЕНС и Налоговый календарь)",
        "description": "Сальдо Единого налогового счета (ЕНС), календарь уплаты ЕНП (28-е число) и контроль рисков приостановления операций (ст. 76 НК РФ).",
        "status": "mock",
        "events_added": 1
    },
    {
        "adapter_name": "bank_centroinvest",
        "display_name": "Банк «Центр-Инвест» (ДБО и АБС)",
        "description": "Прямая интеграция с банком «Центр-Инвест»: графики кредитов, зарплатный проект, предварительно одобренный смарт-овердрафт.",
        "status": "active",
        "events_added": 2
    },
    {
        "adapter_name": "edo_diadoc",
        "display_name": "ЭДО Диадок / СБИС",
        "description": "Подписанные электронные акты, УПД и договоры с автоматическим извлечением условий постоплаты.",
        "status": "mock",
        "events_added": 1
    },
    {
        "adapter_name": "marketplaces",
        "display_name": "Маркетплейсы (WB / Ozon)",
        "description": "Личные кабинеты селлеров: еженедельный график выплат выручки за вычетом комиссии и логистики площадки.",
        "status": "mock",
        "events_added": 1
    }
]

@router.get("/companies/{company_id}/integrations", response_model=List[IntegrationSourceOut])
def list_integrations(company_id: str, db: Session = Depends(get_db)):
    sources = db.query(IntegrationSource).filter(IntegrationSource.company_id == company_id).all()
    if not sources:
        for dic in DEFAULT_INTEGRATION_CONFIGS:
            src = IntegrationSource(
                company_id=company_id,
                adapter_name=dic["adapter_name"],
                display_name=dic["display_name"],
                description=dic["description"],
                status=dic["status"],
                events_added=dic["events_added"],
                last_sync_at=datetime.utcnow()
            )
            db.add(src)
        db.commit()
        sources = db.query(IntegrationSource).filter(IntegrationSource.company_id == company_id).all()
    return sources

@router.post("/companies/{company_id}/integrations/{adapter_name}/sync")
def sync_integration(
    company_id: str,
    adapter_name: str,
    db: Session = Depends(get_db)
):
    """
    Executes integration sync with external system (or realistic mock adapter):
    Pulls real-world structure events into Event table and updates source status.
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    adapter = get_adapter(adapter_name)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Адаптер {adapter_name} не найден")

    # Fetch events
    raw_events = adapter.fetch(company_id=company_id)
    added_count = 0

    for rev in raw_events:
        # Check if event exists
        ev_id = rev["id"]
        existing = db.query(Event).filter(Event.id == ev_id).first()
        if existing:
            existing.event_date = rev["event_date"]
            existing.amount = rev["amount"]
            existing.probability = rev.get("probability", 1.0)
            existing.note = rev.get("note", "")
        else:
            new_ev = Event(
                id=ev_id,
                company_id=company_id,
                event_date=rev["event_date"],
                amount=rev["amount"],
                probability=rev.get("probability", 1.0),
                category_id=rev.get("category_id", "cat_procurement"),
                counterparty_inn=rev.get("counterparty_inn", ""),
                counterparty_name=rev.get("counterparty_name", ""),
                source=adapter_name,
                status="expected",
                note=rev.get("note", "")
            )
            db.add(new_ev)
            added_count += 1

    # Update IntegrationSource record
    src = db.query(IntegrationSource).filter(
        IntegrationSource.company_id == company_id,
        IntegrationSource.adapter_name == adapter_name
    ).first()

    status_info = adapter.status(company_id=company_id)

    if src:
        src.status = "active"
        src.last_sync_at = datetime.utcnow()
        src.events_added += added_count
        src.last_payload = status_info

    db.commit()

    return {
        "status": "success",
        "adapter_name": adapter_name,
        "display_name": adapter.display_name,
        "events_added_this_run": added_count,
        "sync_details": status_info
    }

@router.get("/integrations/registry/check")
def check_counterparty_registry(inn: str = Query(..., description="ИНН контрагента")):
    """
    Open registry check (FR-10.6, ФНС 'Прозрачный бизнес', Федресурс, Арбитраж).
    Detects bankruptcy proceedings and adjusts invoice probability.
    """
    fns = AdapterFNSNalog()
    return fns.verify_counterparty_registry(inn)

# --- 1C & Accounting Export (FR-12.1, FR-12.3) ---
@router.get("/companies/{company_id}/export/1c")
def export_statement_1c(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    ops = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date).all()
    if not ops:
        raise HTTPException(status_code=400, detail="Нет операций для экспорта")

    ops_dicts = [{
        "operation_date": op.operation_date,
        "amount": op.amount,
        "direction": op.direction,
        "counterparty_inn": op.counterparty_inn,
        "counterparty_name": op.counterparty_name,
        "payment_purpose": op.payment_purpose
    } for op in ops[-50:]]  # Last 50 ops

    first_d = ops_dicts[0]["operation_date"]
    last_d = ops_dicts[-1]["operation_date"]
    account_num = f"4070281090000{comp.inn[-6:]}"

    content = generate_1c_client_bank_exchange(
        company_name=comp.name,
        company_inn=comp.inn,
        account_number=account_num,
        date_from=first_d,
        date_to=last_d,
        initial_balance=ops[0].balance_eod,
        final_balance=ops[-1].balance_eod,
        operations=ops_dicts
    )

    return Response(
        content=content.encode("cp1251", errors="replace"),
        media_type="text/plain; charset=windows-1251",
        headers={"Content-Disposition": f"attachment; filename=kl_to_1c_{company_id}.txt"}
    )

@router.get("/companies/{company_id}/export/csv")
def export_statement_csv(company_id: str, db: Session = Depends(get_db)):
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    ops = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Дата", "Направление", "Сумма", "ИНН Контрагента", "Контрагент", "Категория", "Назначение платежа", "Остаток на конец дня"])

    for op in ops:
        writer.writerow([
            op.operation_date.strftime("%Y-%m-%d"),
            op.direction,
            f"{op.amount:.2f}",
            str(op.counterparty_inn or ""),
            op.counterparty_name or "",
            op.category_id or "",
            op.payment_purpose or "",
            f"{op.balance_eod:.2f}"
        ])

    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=operations_{company_id}.csv"}
    )

@router.get("/companies/{company_id}/export/tax-declaration")
def export_tax_declaration(company_id: str, db: Session = Depends(get_db)):
    """
    Выгрузка данных для налоговой декларации / КУДиР (Книга учета доходов и расходов).
    Автоматически разделяет налогооблагаемые доходы (ст. 346.15 НК РФ)
    и учитываемые расходы (ст. 346.16 НК РФ), исключая перемещения между своими счетами.
    """
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    ops = db.query(Operation).filter(Operation.company_id == company_id).order_by(Operation.operation_date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow([f"ВЫГРУЗКА ДЛЯ НАЛОГОВОЙ ДЕКЛАРАЦИИ И КУДиР (УСН / ОСНО)"])
    writer.writerow([f"Организация: {comp.name} | ИНН: {comp.inn} | Налоговый режим: {comp.tax_regime or 'УСН'}"])
    writer.writerow([f"Банковский счет: 40702810...{comp.inn[-4:]} в ПАО КБ Центр-инвест"])
    writer.writerow([])
    writer.writerow([
        "№ п/п",
        "Дата операции",
        "Направление",
        "ИНН Контрагента",
        "Контрагент",
        "Назначение платежа",
        "Категория Кассового радара",
        "Сумма операции (₽)",
        "Доходы, учитываемые при расчете налога (₽)",
        "Расходы, учитываемые при расчете налога (₽)",
        "Квартал",
        "Налоговый статус"
    ])

    total_inflow = 0.0
    total_outflow = 0.0
    taxable_income = 0.0
    deductible_expense = 0.0

    tax_deductible_categories = {
        "cat_procurement", "cat_payroll", "cat_tax_enp",
        "cat_rent_utilities", "cat_bank_credit", "cat_services_marketing", "cat_transport"
    }

    for idx, op in enumerate(ops, 1):
        quarter = f"Q{(op.operation_date.month - 1) // 3 + 1} {op.operation_date.year}"
        
        income_val = 0.0
        expense_val = 0.0
        tax_status = "Учтено в базе"

        if op.category_id == "cat_transfer_own":
            tax_status = "Не облагается (перевод между своими счетами)"
        elif op.direction == "inflow":
            income_val = op.amount
            taxable_income += op.amount
            total_inflow += op.amount
        elif op.direction == "outflow":
            total_outflow += op.amount
            if op.category_id in tax_deductible_categories:
                expense_val = op.amount
                deductible_expense += op.amount
            else:
                tax_status = "Не учитывается в расходах (дивиденды / прочее)"

        writer.writerow([
            idx,
            op.operation_date.strftime("%d.%m.%Y"),
            "Поступление (+)" if op.direction == "inflow" else "Списание (-)",
            str(op.counterparty_inn or ""),
            op.counterparty_name or "",
            (op.payment_purpose or "").replace("\n", " ").strip(),
            op.category_id or "",
            f"{op.amount:.2f}",
            f"{income_val:.2f}" if income_val > 0 else "0.00",
            f"{expense_val:.2f}" if expense_val > 0 else "0.00",
            quarter,
            tax_status
        ])

    writer.writerow([])
    writer.writerow(["--- ИТОГОВЫЕ ПОКАЗАТЕЛИ ДЛЯ НАЛОГОВОЙ ДЕКЛАРАЦИИ ---"])
    writer.writerow(["Всего поступлений на счет", f"{total_inflow:.2f} ₽"])
    writer.writerow(["Всего списаний со счета", f"{total_outflow:.2f} ₽"])
    writer.writerow(["Налогооблагаемые доходы (УСН 6% Доходы)", f"{taxable_income:.2f} ₽"])
    writer.writerow(["Расчетный авансовый налог УСН (6%)", f"{taxable_income * 0.06:.2f} ₽"])
    writer.writerow(["Принимаемые к вычету расходы (УСН 15% Доходы-Расходы)", f"{deductible_expense:.2f} ₽"])
    tax_base_15 = max(0.0, taxable_income - deductible_expense)
    writer.writerow(["Налоговая база УСН Доходы-Расходы (15%)", f"{tax_base_15:.2f} ₽"])
    writer.writerow(["Расчетный авансовый налог УСН (15%)", f"{tax_base_15 * 0.15:.2f} ₽"])

    filename = f"tax_declaration_{company_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
