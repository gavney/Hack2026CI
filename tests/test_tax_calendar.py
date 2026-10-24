from datetime import date
import pytest
from backend.core.tax_calendar import (
    shift_to_next_business_day,
    calculate_tax_calendar_events,
    sync_tax_calendar_events
)
from backend.models import Company, Operation
from backend.database import SessionLocal


def test_weekend_shift_logic():
    # 25 April 2026 is Saturday -> shifts to Monday 27 April
    assert shift_to_next_business_day(date(2026, 4, 25)) == date(2026, 4, 27)
    # 28 April 2026 is Tuesday -> stays 28 April
    assert shift_to_next_business_day(date(2026, 4, 28)) == date(2026, 4, 28)
    # 25 July 2026 is Saturday -> shifts to Monday 27 July
    assert shift_to_next_business_day(date(2026, 7, 25)) == date(2026, 7, 27)
    # 25 October 2026 is Sunday -> shifts to Monday 26 October
    assert shift_to_next_business_day(date(2026, 10, 25)) == date(2026, 10, 26)

    # NDS Calendar weekend shifts:
    # 28 Feb 2026 (Sat) -> 2 March 2026 (Mon)
    assert shift_to_next_business_day(date(2026, 2, 28)) == date(2026, 3, 2)
    # 28 March 2026 (Sat) -> 30 March 2026 (Mon)
    assert shift_to_next_business_day(date(2026, 3, 28)) == date(2026, 3, 30)
    # 28 June 2026 (Sun) -> 29 June 2026 (Mon)
    assert shift_to_next_business_day(date(2026, 6, 28)) == date(2026, 6, 29)
    # 28 Nov 2026 (Sat) -> 30 Nov 2026 (Mon)
    assert shift_to_next_business_day(date(2026, 11, 28)) == date(2026, 11, 30)
    # 28 Feb 2027 (Sun) -> 1 March 2027 (Mon)
    assert shift_to_next_business_day(date(2027, 2, 28)) == date(2027, 3, 1)
    # 28 March 2027 (Sun) -> 29 March 2027 (Mon)
    assert shift_to_next_business_day(date(2027, 3, 28)) == date(2027, 3, 29)


def test_usn_6_percent_calculation():
    comp = Company(id="comp_test_6", name="Тест УСН 6", tax_regime="УСН Доходы 6%", legal_form="ООО")
    ops = [
        Operation(operation_date=date(2026, 1, 15), amount=500000.0, direction="Поступление"),
        Operation(operation_date=date(2026, 3, 20), amount=500000.0, direction="Поступление"),
        Operation(operation_date=date(2026, 2, 1), amount=300000.0, direction="Списание"),
    ]
    events = calculate_tax_calendar_events(comp, ops)
    # In Q1, total inflows = 1,000,000. Tax = 1,000,000 * 6% = 60,000
    q1_payment = next(e for e in events if e["id"].endswith("2026_q1") and e["amount"] < 0)
    assert q1_payment["amount"] == -60000.0
    assert q1_payment["event_date"] == date(2026, 4, 28)

    q1_notif = next(e for e in events if e["id"].endswith("2026_q1") and e["amount"] == 0.0)
    assert q1_notif["event_date"] == date(2026, 4, 27)


def test_usn_15_percent_calculation():
    comp = Company(id="comp_test_15", name="Тест УСН 15", tax_regime="УСН Доходы-Расходы 15%", legal_form="ИП")
    ops = [
        Operation(operation_date=date(2026, 1, 15), amount=1000000.0, direction="Поступление"),
        Operation(operation_date=date(2026, 2, 1), amount=600000.0, direction="Списание"),
    ]
    events = calculate_tax_calendar_events(comp, ops)
    # In Q1: base = 1,000,000 - 600,000 = 400,000. Tax = 400,000 * 15% = 60,000
    q1_payment = next(e for e in events if e["id"].endswith("2026_q1") and e["amount"] < 0)
    assert q1_payment["amount"] == -60000.0


def test_osno_nds_calendar_generation():
    comp = Company(id="comp_test_osno", name="Тест ОСНО", tax_regime="ОСНО (НДС + Прибыль)", legal_form="ООО")
    events = calculate_tax_calendar_events(comp, [])
    # 15 planned notifications
    assert len(events) == 15
    for ev in events:
        assert ev["amount"] == 0.0
        assert "НДС" in ev["note"]
        assert "22%" in ev["note"]


def test_tax_events_db_sync():
    db = SessionLocal()
    comp = db.query(Company).first()
    if comp:
        synced = sync_tax_calendar_events(comp.id, db)
        assert len(synced) > 0
