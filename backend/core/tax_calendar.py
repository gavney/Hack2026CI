"""
Tax Calendar & Quarterly Notifications/Payments Calculation Module.
Handles:
- Weekend shifts: moves Saturday/Sunday forward to the next business day (Monday).
- Tax regimes:
  * УСН Доходы 6%: Quarter tax = quarter_revenue * 0.06
  * УСН Доходы-Расходы 15%: Quarter tax = max(0, quarter_revenue - quarter_expenses) * 0.15
  * ОСНО: VAT (НДС) constant 22% (or company vat_rate); generates planned notification events without amount calculation.
- Quarterly notifications (25th shifted) and payments (28th shifted) for Q1, Q2, Q3.
- Annual tax (Налог за год):
  * Declaration: by March 25 (organizations) / April 25 (IP), shifted to next business day.
  * Payment: by March 28 (organizations) / April 28 (IP), shifted to next business day.
  * Tax amount: total year tax minus advances paid in Q1, Q2, Q3.
- NDS payment calendar: 15 payments across IV Q 2025 and I-IV Q 2026.
"""

from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models import Company, Operation, Event


def shift_to_next_business_day(d: date) -> date:
    """
    If date falls on weekend (Saturday=5, Sunday=6),
    shift forward to the nearest business day (Monday).
    """
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def calculate_tax_calendar_events(company: Company, operations: List[Operation]) -> List[Dict[str, Any]]:
    tax_regime = (company.tax_regime or "УСН Доходы 6%").strip()
    legal_form = (company.legal_form or "").upper().strip()
    is_ip = "ИП" in legal_form
    vat_rate = getattr(company, "vat_rate", 22.0) or 22.0

    events: List[Dict[str, Any]] = []

    is_usn_6 = "6%" in tax_regime or "ДОХОДЫ 6" in tax_regime.upper()
    is_usn_15 = "15%" in tax_regime or "15" in tax_regime
    is_osno = "ОСНО" in tax_regime.upper() or "НДС" in tax_regime.upper()

    if is_usn_6 or is_usn_15:
        # Determine relevant years from operations or default to 2026
        op_years = {op.operation_date.year for op in operations if op.operation_date}
        target_years = sorted(list(op_years)) if op_years else [2026]
        if 2026 not in target_years:
            target_years.append(2026)

        regime_title = "УСН 6%" if is_usn_6 else "УСН 15%"

        for year in target_years:
            # We focus on the active year (e.g. 2026 or latest)
            if year < 2025:
                continue

            # Quarter definitions:
            # Q1: 01.01 - 31.03 (Notif: 25 Apr, Pay: 28 Apr)
            # Q2: 01.04 - 30.06 (Notif: 25 Jul, Pay: 28 Jul)
            # Q3: 01.07 - 30.09 (Notif: 25 Oct, Pay: 28 Oct)
            q_bounds = {
                1: (date(year, 1, 1), date(year, 3, 31), date(year, 4, 25), date(year, 4, 28)),
                2: (date(year, 4, 1), date(year, 6, 30), date(year, 7, 25), date(year, 7, 28)),
                3: (date(year, 7, 1), date(year, 9, 30), date(year, 10, 25), date(year, 10, 28)),
            }

            year_inflow = 0.0
            year_outflow = 0.0
            q_advances = {}

            for q, (q_start, q_end, notif_raw, pay_raw) in q_bounds.items():
                q_ops = [op for op in operations if op.operation_date and q_start <= op.operation_date <= q_end]
                q_inflow = sum(op.amount for op in q_ops if op.direction == 'Поступление')
                q_outflow = sum(op.amount for op in q_ops if op.direction == 'Списание')

                year_inflow += q_inflow
                year_outflow += q_outflow

                if is_usn_6:
                    tax_amt = round(q_inflow * 0.06, 2)
                    calc_details = f"Доход за {q} кв.: {q_inflow:,.2f} ₽ × 6%".replace(",", " ")
                else:
                    tax_base = max(0.0, q_inflow - q_outflow)
                    tax_amt = round(tax_base * 0.15, 2)
                    calc_details = f"База ({q_inflow:,.2f} − {q_outflow:,.2f}) ₽ × 15%".replace(",", " ")

                q_advances[q] = tax_amt
                notif_date = shift_to_next_business_day(notif_raw)
                pay_date = shift_to_next_business_day(pay_raw)

                # 1. Planned Notification Event (Уведомление об исчисленных суммах)
                events.append({
                    "id": f"tax_notif_usn_{company.id}_{year}_q{q}",
                    "company_id": company.id,
                    "event_date": notif_date,
                    "amount": 0.0,
                    "probability": 1.0,
                    "category_id": "cat_tax_enp",
                    "counterparty_name": "ФНС России (ЕНС)",
                    "counterparty_inn": "7707329152",
                    "source": "tax_calendar",
                    "status": "expected",
                    "is_active": True,
                    "note": f"Налоги по УСН/НДС | Уведомление об исчисленных суммах авансовых платежей за {q} кв. {year} г. ({regime_title}: {tax_amt:,.2f} ₽ • {calc_details})",
                })

                # 2. Planned Tax Payment Event (Уплата авансового платежа)
                events.append({
                    "id": f"tax_pay_usn_{company.id}_{year}_q{q}",
                    "company_id": company.id,
                    "event_date": pay_date,
                    "amount": -abs(tax_amt),
                    "probability": 1.0,
                    "category_id": "cat_tax_enp",
                    "counterparty_name": "ФНС России (ЕНС)",
                    "counterparty_inn": "7707329152",
                    "source": "tax_calendar",
                    "status": "expected",
                    "is_active": True,
                    "note": f"Налоги по УСН/НДС | Уплата авансового платежа по {regime_title} за {q} квартал {year} г. ({calc_details})",
                })

            # Q4 and Annual Tax Calculation:
            # За 4 квартал отдельно аванс не платится. Платится налог за год.
            q4_ops = [op for op in operations if op.operation_date and date(year, 10, 1) <= op.operation_date <= date(year, 12, 31)]
            year_inflow += sum(op.amount for op in q4_ops if op.direction == 'Поступление')
            year_outflow += sum(op.amount for op in q4_ops if op.direction == 'Списание')

            if is_usn_6:
                total_year_tax = round(year_inflow * 0.06, 2)
                year_calc_details = f"Годовой доход: {year_inflow:,.2f} ₽ × 6%".replace(",", " ")
            else:
                total_year_tax = round(max(0.0, year_inflow - year_outflow) * 0.15, 2)
                year_calc_details = f"Годовая база ({year_inflow:,.2f} − {year_outflow:,.2f}) ₽ × 15%".replace(",", " ")

            paid_advances = sum(q_advances.values())
            remaining_year_tax = max(0.0, round(total_year_tax - paid_advances, 2))

            # Annual deadlines:
            # Declaration: March 25 (org) / April 25 (IP)
            # Payment: March 28 (org) / April 28 (IP)
            decl_raw = date(year + 1, 4, 25) if is_ip else date(year + 1, 3, 25)
            pay_year_raw = date(year + 1, 4, 28) if is_ip else date(year + 1, 3, 28)

            decl_date = shift_to_next_business_day(decl_raw)
            pay_year_date = shift_to_next_business_day(pay_year_raw)

            # 3. Year-end Declaration Event
            events.append({
                "id": f"tax_decl_usn_{company.id}_{year}",
                "company_id": company.id,
                "event_date": decl_date,
                "amount": 0.0,
                "probability": 1.0,
                "category_id": "cat_tax_enp",
                "counterparty_name": "ФНС России (ЕНС)",
                "counterparty_inn": "7707329152",
                "source": "tax_calendar",
                "status": "expected",
                "is_active": True,
                "note": f"Налоги по УСН/НДС | Подача декларации по {regime_title} за {year} г. (Остаток налога к доплате: {remaining_year_tax:,.2f} ₽ • {year_calc_details})",
            })

            # 4. Year-end Tax Payment Event
            events.append({
                "id": f"tax_pay_usn_{company.id}_{year}_final",
                "company_id": company.id,
                "event_date": pay_year_date,
                "amount": -abs(remaining_year_tax),
                "probability": 1.0,
                "category_id": "cat_tax_enp",
                "counterparty_name": "ФНС России (ЕНС)",
                "counterparty_inn": "7707329152",
                "source": "tax_calendar",
                "status": "expected",
                "is_active": True,
                "note": f"Налоги по УСН/НДС | Уплата налога по {regime_title} за {year} год (итог за вычетом авансов: {remaining_year_tax:,.2f} ₽)",
            })

    elif is_osno:
        # ОСНО: НДС Налоговый календарь (15 платежей по расписанию)
        nds_schedule = [
            ("IV квартал 2025, 1-й платёж", date(2026, 1, 28)),
            ("IV квартал 2025, 2-й платёж", date(2026, 3, 2)),
            ("IV квартал 2025, 3-й платёж", date(2026, 3, 30)),
            ("I квартал 2026, 1-й платёж", date(2026, 4, 28)),
            ("I квартал 2026, 2-й платёж", date(2026, 5, 28)),
            ("I квартал 2026, 3-й платёж", date(2026, 6, 29)),
            ("II квартал 2026, 1-й платёж", date(2026, 7, 28)),
            ("II квартал 2026, 2-й платёж", date(2026, 8, 28)),
            ("II квартал 2026, 3-й платёж", date(2026, 9, 28)),
            ("III квартал 2026, 1-й платёж", date(2026, 10, 28)),
            ("III квартал 2026, 2-й платёж", date(2026, 11, 30)),
            ("III квартал 2026, 3-й платёж", date(2026, 12, 28)),
            ("IV квартал 2026, 1-й платёж", date(2027, 1, 28)),
            ("IV квартал 2026, 2-й платёж", date(2027, 3, 1)),
            ("IV квартал 2026, 3-й платёж", date(2027, 3, 29)),
        ]

        for idx, (title, dt) in enumerate(nds_schedule, start=1):
            shifted_dt = shift_to_next_business_day(dt)
            events.append({
                "id": f"tax_notif_nds_{company.id}_{idx}",
                "company_id": company.id,
                "event_date": shifted_dt,
                "amount": 0.0,  # Для НДС создаются плановые уведомления без прямого расчета
                "probability": 1.0,
                "category_id": "cat_tax_enp",
                "counterparty_name": "ФНС России (ЕНС НДС)",
                "counterparty_inn": "7707329152",
                "source": "tax_calendar",
                "status": "expected",
                "is_active": True,
                "note": f"Налоги по УСН/НДС | {title} (ставка НДС {int(vat_rate)}% • плановое уведомление/уплата)",
            })

    return events


def sync_tax_calendar_events(company_id: str, db: Session) -> List[Event]:
    """
    Cleans up auto-generated tax calendar events and recalculates them from operations.
    Leaves user manual events intact.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return []

    operations = db.query(Operation).filter(Operation.company_id == company_id).all()
    calculated_data = calculate_tax_calendar_events(company, operations)

    # Delete previous auto-generated events for this company
    db.query(Event).filter(
        Event.company_id == company_id,
        Event.source == "tax_calendar"
    ).delete(synchronize_session=False)

    new_events = []
    for item in calculated_data:
        ev = Event(**item)
        new_events.append(ev)

    db.add_all(new_events)
    db.commit()

    return new_events
