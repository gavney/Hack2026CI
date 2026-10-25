import pytest
import io
import pandas as pd
from datetime import date
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.forecaster import MLForecaster
from backend.routers.forecast import FORECASTER_REGISTRY
from backend.core.ai_categorizer import cascade_categorizer, extract_contract_data_with_ai

client = TestClient(app)

def test_ml_forecaster_direct():
    forecaster = MLForecaster()
    # 40 days of history
    dates = pd.date_range("2025-01-01", periods=40, freq="D")
    records = []
    bal = 500000.0
    for d in dates:
        amt_in = 20000.0 if d.dayofweek < 5 else 5000.0
        amt_out = 15000.0 if d.dayofweek < 5 else 2000.0
        bal = bal + amt_in - amt_out
        records.append({
            "operation_date": d.date(),
            "amount": amt_in,
            "direction": "Поступление",
            "category_id": "cat_revenue_client",
            "balance_eod": bal
        })
        records.append({
            "operation_date": d.date(),
            "amount": amt_out,
            "direction": "Списание",
            "category_id": "cat_procurement",
            "balance_eod": bal
        })
    df_history = pd.DataFrame(records)

    res = forecaster.forecast(
        history=df_history,
        balance_as_of=bal,
        as_of=dates[-1].date(),
        horizon=30,
        overdraft_limit=50000.0,
        seed=42
    )

    assert res["model_version"] == "ml-ridge-lgbm-v1.0"
    assert res["quality"] in ("high", "medium")
    assert len(res["days"]) == 30
    assert "simulation_meta" in res
    assert res["simulation_meta"]["engine"] == "ml-ridge-lgbm"

    # Monotonicity check
    for day in res["days"]:
        assert day["p10"] <= day["p50"], f"p10 {day['p10']} > p50 {day['p50']}"
        assert day["p50"] <= day["p90"], f"p50 {day['p50']} > p90 {day['p90']}"
        assert 0.0 <= day["prob_negative"] <= 1.0


def test_forecast_api_with_ml_model():
    res = client.get("/api/companies/C001/forecast?horizon=30&model=ml-ridge-lgbm")
    assert res.status_code == 200
    data = res.json()
    assert data["model_version"] in ("ml-ridge-lgbm-v1.0", "clean-business")
    assert len(data["days"]) == 30


def test_forecast_settings_api():
    # GET settings
    res = client.get("/api/companies/C001/forecast-settings")
    assert res.status_code == 200
    data = res.json()
    assert "forecast_model" in data
    assert "available_models" in data
    assert "ml-ridge-lgbm" in data["available_models"]

    # PATCH settings to monte-carlo
    patch_res = client.patch("/api/companies/C001/forecast-settings", json={
        "forecast_model": "monte-carlo",
        "forecast_confidence_level": 0.95
    })
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["forecast_model"] == "monte-carlo"
    assert updated["forecast_confidence_level"] == 0.95

    # Switch back to ML model
    client.patch("/api/companies/C001/forecast-settings", json={
        "forecast_model": "ml-ridge-lgbm"
    })


def test_cascade_categorization_and_vat():
    # 1. Mandatory outflow flagged as cash gap critical
    c1, conf1, src1, is_crit1, vat_flag1, vat_amt1 = cascade_categorizer.classify_single(
        direction="Списание",
        purpose="Выплата заработной платы за апрель 2026 по реестру № 12",
        counterparty_inn="7701234567"
    )
    assert c1 == "cat_payroll"
    assert is_crit1 is True
    assert src1 == "rule"

    # 2. Inflow with VAT
    c2, conf2, src2, is_crit2, vat_flag2, vat_amt2 = cascade_categorizer.classify_single(
        direction="Поступление",
        purpose="Оплата по договору № 45 за строительные материалы. В т.ч. НДС 20% 48000.00 руб.",
        counterparty_inn="7709876543"
    )
    assert c2 == "cat_revenue_client"
    assert is_crit2 is False
    assert vat_flag2 == 1
    assert vat_amt2 == 48000.0

    # 3. Inflow exempt from VAT
    c3, conf3, src3, is_crit3, vat_flag3, vat_amt3 = cascade_categorizer.classify_single(
        direction="Поступление",
        purpose="Оплата медицинских услуг по счету 11. НДС не облагается.",
        counterparty_inn="7709876543"
    )
    assert c3 == "cat_revenue_client"
    assert vat_flag3 == 0


def test_contract_upload_and_event_creation():
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 100),
        "ДОГОВОР ПОСТАВКИ № 10\n"
        "Общая стоимость договора составляет 250000.00 рублей.\n"
        "Срок оплаты производится до 28.11.2026.\n"
        "Договор действует в течение года (ежемесячно).\n"
        "Исполнитель: ООО Снабжение, ИНН: 7701234567\n"
        "Заказчик: ООО Вектор, ИНН: 7709876543\n"
    )
    pdf_bytes = doc.tobytes()

    files = {"file": ("dogovor_postavki.pdf", pdf_bytes, "application/pdf")}
    res = client.post("/api/companies/C001/upload-contract", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "event_id" in data
    assert "contract_data" in data
    assert data["contract_data"]["cost"] == 250000.0
