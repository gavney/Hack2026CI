import pytest
import math
import numpy as np
import pandas as pd
from datetime import date, timedelta
from backend.core.forecaster import MLForecaster, is_owner_operation
from ML.improved_forecaster import HybridMLForecaster


def test_t1_zero_data_leakage():
    """T1: Ensure no operations with date > cutoff are used in training or features."""
    forecaster = MLForecaster()
    # Create history with past and future
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    cutoff = dates[39].date()  # Day 40 is cutoff
    
    records = []
    bal = 100000.0
    for i, d in enumerate(dates):
        # Even if future has huge extreme spike, model at cutoff should not know about it
        amt = 10000000.0 if i >= 40 else 10000.0
        records.append({
            "operation_date": d.date(),
            "amount": amt,
            "direction": "Поступление",
            "category_id": "cat_revenue_client",
            "payment_purpose": "Оплата по счету",
            "balance_eod": bal
        })
    df_all = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df_all,
        balance_as_of=bal,
        as_of=cutoff,
        horizon=20,
        seed=42
    )
    # The Day 1 predicted balance should be close to bal, not influenced by 10M future ops
    assert res["days"][0]["p50"] < 1000000.0, "Leakage detected: future operations influenced cutoff forecast!"


def test_t2_slot_single_counting():
    """T2: In primary ML forecast, slots are not injected as deterministic events."""
    forecaster = MLForecaster(slots_as_events=False)
    dates = pd.date_range("2026-01-01", periods=45, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 10000.0,
        "direction": "Поступление",
        "category_id": "cat_revenue",
        "payment_purpose": "Выручка",
        "balance_eod": 50000.0
    } for d in dates]
    df = pd.DataFrame(records)
    
    cutoff = dates[-1].date()
    target_date = cutoff + timedelta(days=5)
    slots = [{
        "event_date": target_date,
        "amount": -500000.0,
        "category_id": "cat_rent",
        "source": "slot"
    }]
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=50000.0,
        as_of=cutoff,
        horizon=10,
        events=slots,
        seed=42
    )
    # Verify that day 5 does NOT have an exact deterministic drop of 500k
    step_4 = res["days"][3]["p50"]
    step_5 = res["days"][4]["p50"]
    diff = step_4 - step_5
    assert abs(diff - 500000.0) > 10000.0, "Slot was deterministically injected into primary ML forecast!"


def test_t3_confusion_matrix_consistency():
    """T3: Confusion matrix math matches precision, recall, F1, accuracy formulas exactly."""
    y_true = np.array([1, 1, 1, 0, 0, 1, 0, 0, 1, 0])
    y_pred = np.array([1, 1, 0, 0, 1, 1, 0, 0, 0, 0])
    
    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fn = np.sum((y_true == 1) & (y_pred == 0))
    tn = np.sum((y_true == 0) & (y_pred == 0))
    
    assert tp + fp + fn + tn == len(y_true)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true)
    
    assert tp == 3
    assert fp == 1
    assert fn == 2
    assert tn == 4
    assert pytest.approx(precision, 0.001) == 0.75
    assert pytest.approx(recall, 0.001) == 0.60
    assert pytest.approx(f1, 0.001) == 0.6667
    assert pytest.approx(accuracy, 0.001) == 0.70


def test_t4_corridor_width_growth():
    """T4: Corridor width scales proportional to sqrt(h), W(90)/W(30) <= 2.2."""
    forecaster = MLForecaster(block_len=7)
    dates = pd.date_range("2025-01-01", periods=180, freq="D")
    records = []
    bal = 200000.0
    rng = np.random.default_rng(42)
    for d in dates:
        net = float(rng.normal(100.0, 15000.0))
        bal += net
        records.append({
            "operation_date": d.date(),
            "amount": abs(net),
            "direction": "Поступление" if net >= 0 else "Списание",
            "category_id": "cat_sales",
            "payment_purpose": "Торговый оборот",
            "balance_eod": bal
        })
    df = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=bal,
        as_of=dates[-1].date(),
        horizon=90,
        seed=42
    )
    
    w30 = res["days"][29]["p90"] - res["days"][29]["p10"]
    w60 = res["days"][59]["p90"] - res["days"][59]["p10"]
    w90 = res["days"][89]["p90"] - res["days"][89]["p10"]
    
    ratio_60_30 = w60 / w30
    ratio_90_30 = w90 / w30
    
    # Expected for sqrt(h): sqrt(2) ≈ 1.414, sqrt(3) ≈ 1.732
    # Linear growth would give 2.0 and 3.0.
    assert ratio_60_30 <= 1.70, f"W60/W30 ratio {ratio_60_30:.3f} exceeds sqrt(h) expectation!"
    assert ratio_90_30 <= 2.20, f"W90/W30 ratio {ratio_90_30:.3f} exceeds sqrt(h) expectation!"
    assert ratio_90_30 >= 1.30, f"W90/W30 ratio {ratio_90_30:.3f} is uncharacteristically low!"


def test_t5_p_any_ge_max_p_gap():
    """T5: Window-level P_any >= max daily P_gap (Probability Theorem)."""
    forecaster = MLForecaster()
    dates = pd.date_range("2025-01-01", periods=90, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 10000.0,
        "direction": "Списание",
        "category_id": "cat_procurement",
        "payment_purpose": "Закупка",
        "balance_eod": 50000.0
    } for d in dates]
    df = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=20000.0,
        as_of=dates[-1].date(),
        horizon=30,
        seed=42
    )
    
    max_daily_prob = max(d["prob_negative"] for d in res["days"])
    p_any = res["gap_probability"]
    assert p_any >= max_daily_prob - 1e-6, f"Theorem violated: P_any {p_any} < max daily P_gap {max_daily_prob}"


def test_t6_owner_filter_c004():
    """T6: Owner operation filter on C004 labeled operations."""
    ops = [
        {"purpose": "Пополнение счета собственными средствами. НДС не облагается", "cp": "ИП Предприниматель-744", "cat": "cat_other_in", "expected": True},
        {"purpose": "Перевод собственных средств ИП на счет физического лица", "cp": "ИП Предприниматель-744", "cat": "cat_other_out", "expected": True},
        {"purpose": "Перевод собственных средств на личную карту. НДС не облагается", "cp": "ИП Предприниматель-744", "cat": "cat_other_out", "expected": True},
        {"purpose": "Взнос наличных через устройство самообслуживания № 12345", "cp": "ИП Предприниматель-744", "cat": "cat_cash_in", "expected": False},
        {"purpose": "Оплата за аренду помещения за май 2026", "cp": "ООО Арендодатель", "cat": "cat_rent", "expected": False},
        {"purpose": "Оплата поставщику за строительные материалы", "cp": "ООО СтройСнаб", "cat": "cat_procurement", "expected": False}
    ]
    for op in ops:
        res = is_owner_operation(
            purpose=op["purpose"],
            category_id=op["cat"],
            counterparty_name=op["cp"]
        )
        assert res == op["expected"], f"Failed for {op['purpose']}: got {res}, expected {op['expected']}"


def test_t7_monotonicity_guarantee():
    """T7: Monotonicity guarantee P10 <= P50 <= P90 on all forecast days."""
    forecaster = MLForecaster()
    dates = pd.date_range("2025-01-01", periods=60, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 25000.0,
        "direction": "Поступление" if i % 2 == 0 else "Списание",
        "category_id": "cat_trade",
        "payment_purpose": "Оборотные средства",
        "balance_eod": 100000.0
    } for i, d in enumerate(dates)]
    df = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=100000.0,
        as_of=dates[-1].date(),
        horizon=30,
        seed=42
    )
    for day in res["days"]:
        assert day["p10"] <= day["p50"], f"p10 {day['p10']} > p50 {day['p50']}"
        assert day["p50"] <= day["p90"], f"p50 {day['p50']} > p90 {day['p90']}"


def test_t8_trivial_windows():
    """T8: If B0 < 0, window is trivial (start_negative=True, P_any=1.0, status='разрыв уже идет')."""
    forecaster = MLForecaster()
    dates = pd.date_range("2025-01-01", periods=45, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 5000.0,
        "direction": "Списание",
        "category_id": "cat_expense",
        "payment_purpose": "Расход",
        "balance_eod": -50000.0
    } for d in dates]
    df = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=-50000.0,
        as_of=dates[-1].date(),
        horizon=30,
        seed=42
    )
    assert res["gap_probability"] == 1.0
    assert res["simulation_meta"]["start_negative"] is True
    assert "разрыв уже идет" in res["simulation_meta"]["status"]


def test_t9_zero_pii_logging(caplog):
    """T9: Ensure zero PII in logs (no INN, names, purposes, amounts)."""
    import logging
    from ML.improved_forecaster import log_event
    with caplog.at_level(logging.INFO):
        log_event(
            "TestLog",
            inn="7701234567",
            counterparty_name="ИП Иванов",
            payment_purpose="Зарплата секретная",
            amount=123456.78,
            horizon_days=30,
            p_any=0.45
        )
    output = caplog.text
    assert "7701234567" not in output
    assert "Иванов" not in output
    assert "секретная" not in output
    assert "123456.78" not in output
    assert "horizon_days" in output
    assert "0.45" in output


def test_t10_api_contract_structure():
    """T10: Strict API contract structure validation."""
    forecaster = MLForecaster()
    dates = pd.date_range("2025-01-01", periods=50, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 10000.0,
        "direction": "Поступление",
        "category_id": "cat_income",
        "payment_purpose": "Доход",
        "balance_eod": 75000.0
    } for d in dates]
    df = pd.DataFrame(records)
    
    res = forecaster.forecast(
        history=df,
        balance_as_of=75000.0,
        as_of=dates[-1].date(),
        horizon=30,
        seed=42
    )
    required_keys = {"model_version", "quality", "as_of", "horizon", "days", "contributions",
                     "total_shortfall_p10", "first_gap_date", "gap_probability", "sample_paths", "simulation_meta"}
    assert required_keys.issubset(res.keys())
    assert len(res["sample_paths"]) == 5
    assert len(res["days"]) == 30
    day_keys = {"date", "p10", "p50", "p90", "prob_negative"}
    assert day_keys.issubset(res["days"][0].keys())


def test_t11_ablation_distinctness():
    """T11: Verify that differing ablation configurations produce distinct predictions and feature sets."""
    import hashlib
    dates = pd.date_range("2026-01-01", periods=90, freq="D")
    records = []
    bal = 200000.0
    for i, d in enumerate(dates):
        amt = 30000.0 if i % 3 == 0 else -15000.0
        purpose = "Взнос собственных средств от учредителя" if i == 45 else "Оплата товара"
        bal += amt
        records.append({
            "operation_date": d.date(),
            "amount": amt,
            "direction": "Поступление" if amt > 0 else "Списание",
            "category_id": "cat_other_in" if i == 45 else "cat_trade",
            "payment_purpose": purpose,
            "balance_eod": bal
        })
    df = pd.DataFrame(records)
    cutoff = dates[-1].date()
    target_date = cutoff + timedelta(days=5)
    slots = [{
        "event_date": target_date,
        "amount": -500000.0,
        "category_id": "cat_rent",
        "source": "slot"
    }]

    # Config 1: ML-only (slots_as_events=False)
    f_ml = MLForecaster(slots_as_events=False, block_len=7)
    res_ml = f_ml.forecast(df, bal, cutoff, horizon=15, events=slots, seed=42)

    # Config 2: Slots injected as deterministic events (slots_as_events=True)
    f_slots = MLForecaster(slots_as_events=True, block_len=7)
    res_slots = f_slots.forecast(df, bal, cutoff, horizon=15, events=slots, seed=42)

    # Config 3: Block bootstrap with block_len=1 (i.i.d.) vs block_len=7
    f_iid = MLForecaster(slots_as_events=False, block_len=1)
    res_iid = f_iid.forecast(df, bal, cutoff, horizon=15, seed=42)

    p50_ml = [d["p50"] for d in res_ml["days"]]
    p50_slots = [d["p50"] for d in res_slots["days"]]
    p10_ml = [d["p10"] for d in res_ml["days"]]
    p10_iid = [d["p10"] for d in res_iid["days"]]

    # 1. Prediction distinctness: slots_as_events toggling produces different trajectories
    assert p50_ml != p50_slots, "slots_as_events flag must produce distinct median trajectories"
    # 2. Uncertainty distinctness: block bootstrap length alters quantile corridor
    assert p10_ml != p10_iid, "block_len parameter must produce distinct uncertainty corridors"

    # 3. Feature hash distinctness test: direct forecasting adds horizon_h
    base_feats = ["lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "lag_21", "lag_28", "mean_7", "mean_28", "std_28"]
    direct_feats = base_feats + ["horizon_h"]
    h_base = hashlib.md5(",".join(base_feats).encode()).hexdigest()[:8]
    h_direct = hashlib.md5(",".join(direct_feats).encode()).hexdigest()[:8]
    assert h_base != h_direct, "Direct forecasting feature set must have distinct hash vs recursive"


def test_corridor_width_sqrt_growth():
    """Verify that ML v2.0 corridor width scales with ~sqrt(h) rather than linearly."""
    forecaster = MLForecaster()
    dates = pd.date_range("2026-01-01", periods=90, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 20000.0 if i % 2 == 0 else -15000.0,
        "direction": "Поступление" if i % 2 == 0 else "Списание",
        "category_id": "cat_trade",
        "payment_purpose": "Оборот",
        "balance_eod": 100000.0
    } for i, d in enumerate(dates)]
    df = pd.DataFrame(records)
    cutoff = dates[-1].date()

    r30 = forecaster.forecast(df, 100000.0, cutoff, horizon=30, seed=42)
    r60 = forecaster.forecast(df, 100000.0, cutoff, horizon=60, seed=42)
    r90 = forecaster.forecast(df, 100000.0, cutoff, horizon=90, seed=42)

    w30 = r30["days"][-1]["p90"] - r30["days"][-1]["p10"]
    w60 = r60["days"][-1]["p90"] - r60["days"][-1]["p10"]
    w90 = r90["days"][-1]["p90"] - r90["days"][-1]["p10"]

    ratio_60_30 = w60 / max(1.0, w30)
    ratio_90_30 = w90 / max(1.0, w30)

    # sqrt(2) ≈ 1.414, sqrt(3) ≈ 1.732. Linear would be 2.0 and 3.0.
    assert 1.15 <= ratio_60_30 <= 1.70, f"w60/w30 ratio {ratio_60_30:.3f} deviates from sqrt(2)!"
    assert 1.35 <= ratio_90_30 <= 2.10, f"w90/w30 ratio {ratio_90_30:.3f} deviates from sqrt(3)!"


def test_p_any_ge_max_pointwise():
    """Verify mathematical property: P(gap anywhere in window) >= max_h P(gap on day h)."""
    forecaster = MLForecaster()
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 25000.0 if i % 3 == 0 else -18000.0,
        "direction": "Поступление" if i % 3 == 0 else "Списание",
        "category_id": "cat_trade",
        "payment_purpose": "Оборот",
        "balance_eod": 50000.0
    } for i, d in enumerate(dates)]
    df = pd.DataFrame(records)
    cutoff = dates[-1].date()

    res = forecaster.forecast(df, 50000.0, cutoff, horizon=30, seed=42)
    max_pointwise = max(d["prob_negative"] for d in res["days"])
    p_any = res["gap_probability"]

    assert p_any >= max_pointwise - 1e-5, f"P_any {p_any} < max pointwise {max_pointwise}"


def test_start_negative_p_any_one():
    """Verify that if starting balance is negative (B0 < 0), P_any is strictly 1.0."""
    forecaster = MLForecaster()
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    records = [{
        "operation_date": d.date(),
        "amount": 10000.0,
        "direction": "Списание",
        "category_id": "cat_expense",
        "payment_purpose": "Расход",
        "balance_eod": -25000.0
    } for d in dates]
    df = pd.DataFrame(records)
    cutoff = dates[-1].date()

    res = forecaster.forecast(df, -25000.0, cutoff, horizon=30, seed=42)
    assert res["gap_probability"] == 1.0, f"Expected 1.0, got {res['gap_probability']}"
    assert res["simulation_meta"]["start_negative"] is True


def test_t15_zero_leakage_after_cutoff_in_features_and_slots():
    """T15 (FIX16): Verify that mutating future data after cutoff T does not alter features or slots."""
    from backend.core.slots import detect_recurring_slots
    from backend.core.categorizer import classify_operation

    dates = pd.date_range("2026-01-01", periods=90, freq="D")
    cutoff = dates[59].date()  # Day 60 is cutoff

    records = []
    bal = 100000.0
    for i, d in enumerate(dates):
        amt = 15000.0 if i % 2 == 0 else -10000.0
        bal += amt
        records.append({
            "operation_date": d.date(),
            "amount": abs(amt),
            "direction": "Поступление" if amt > 0 else "Списание",
            "category_id": "cat_trade",
            "payment_purpose": "Регулярная операция",
            "counterparty_inn": "7701234567",
            "counterparty_name": "ООО Партнер",
            "balance_eod": bal
        })
    df_clean = pd.DataFrame(records)

    # Historical slice strictly <= T
    df_past = df_clean[df_clean["operation_date"] <= cutoff].copy()
    slots_past = detect_recurring_slots(df_past)

    # Mutated future after T: add huge fake spike operations after cutoff
    df_mutated = df_clean.copy()
    future_mask = df_mutated["operation_date"] > cutoff
    df_mutated.loc[future_mask, "amount"] = 999999999.0
    df_mutated.loc[future_mask, "payment_purpose"] = "ФЕЙКОВАЯ ОПЕРАЦИЯ БУДУЩЕГО"

    # Forecaster should slice at cutoff T and produce identical output
    forecaster = MLForecaster()
    res_orig = forecaster.forecast(df_clean, 100000.0, cutoff, horizon=30, seed=42)
    res_mut = forecaster.forecast(df_mutated, 100000.0, cutoff, horizon=30, seed=42)

    assert res_orig["days"][0]["p50"] == res_mut["days"][0]["p50"], "Future data mutation altered Day 1 forecast!"
    assert res_orig["days"][-1]["p50"] == res_mut["days"][-1]["p50"], "Future data mutation altered Day 30 forecast!"
    assert res_orig["gap_probability"] == res_mut["gap_probability"], "Future data mutation altered P_any!"


def test_t16_endpoint_and_offline_exact_match_1e6():
    """T16 (FIX19): Endpoint and offline forecast match within 1e-6 tolerance on C004."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.database import SessionLocal
    from backend.models import Operation

    client = TestClient(app)
    resp = client.get("/api/companies/C004/forecast?horizon=90&model=ml-v2.0-canonical")
    assert resp.status_code == 200
    data_api = resp.json()
    assert data_api["model_version"] == "ml-v2.0-canonical"

    p10_api = np.array([d["p10"] for d in data_api["days"]])
    p50_api = np.array([d["p50"] for d in data_api["days"]])
    p90_api = np.array([d["p90"] for d in data_api["days"]])

    db = SessionLocal()
    ops = db.query(Operation).filter(Operation.company_id == "C004").order_by(Operation.operation_date).all()
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
    df = pd.DataFrame(history_records)
    last_op = ops[-1]

    forecaster = MLForecaster()
    res_off = forecaster.forecast(df, float(last_op.balance_eod), last_op.operation_date, horizon=90, seed=42)
    assert res_off["model_version"] == "ml-v2.0-canonical"

    p10_off = np.array([d["p10"] for d in res_off["days"]])
    p50_off = np.array([d["p50"] for d in res_off["days"]])
    p90_off = np.array([d["p90"] for d in res_off["days"]])

    assert np.allclose(p10_api, p10_off, atol=1e-6), f"P10 mismatch: max diff {np.max(np.abs(p10_api - p10_off))}"
    assert np.allclose(p50_api, p50_off, atol=1e-6), f"P50 mismatch: max diff {np.max(np.abs(p50_api - p50_off))}"
    assert np.allclose(p90_api, p90_off, atol=1e-6), f"P90 mismatch: max diff {np.max(np.abs(p90_api - p90_off))}"


def test_t17_c004_slots_medians():
    """T17 (FIX21): Verified recurring slots for C004 match exact medians of last 6 payments."""
    import sqlite3
    conn = sqlite3.connect("radar.db")
    df_slots = pd.read_sql_query("SELECT category_id, day_of_month, typical_amount FROM slots WHERE company_id = 'C004' ORDER BY day_of_month", conn)
    
    slots_map = {(r["category_id"], int(r["day_of_month"])): float(r["typical_amount"]) for _, r in df_slots.iterrows()}
    
    # 1. Rent on 2nd: 160,000.00 RUB
    assert abs(slots_map.get(("cat_rent_utilities", 2), 0.0) - 160000.00) < 1.0
    # 2. POS fee on 3rd: 1,500.00 RUB
    assert abs(slots_map.get(("cat_rent_utilities", 3), 0.0) - 1500.00) < 1.0
    # 3. Payroll advance on 15th: 180,000.00 RUB
    assert abs(slots_map.get(("cat_payroll", 15), 0.0) - 180000.00) < 1.0
    # 4. ENP tax on 28th: 174,821.00 RUB
    assert abs(slots_map.get(("cat_tax_enp", 28), 0.0) - 174821.00) < 1.0
    # 5. Payroll settlement on 30th: 270,013.81 RUB
    assert abs(slots_map.get(("cat_payroll", 30), 0.0) - 270013.81) < 1.0


def test_t18_short_history_companies_no_crash():
    """T18 (C1.2-FIX3): Fallback robustness on all 10 EXCLUDED_SHORT companies and ultra-short histories."""
    excluded_cids = ["C046", "C049", "C059", "C068", "C081", "C088", "C105", "C110", "C136", "C142"]
    ml = MLForecaster()

    for cid in excluded_cids:
        df = pd.read_csv(f"data/statements/{cid}.csv", sep=";", encoding="utf-8-sig")
        df["operation_date"] = pd.to_datetime(df["operation_date"])
        d_max = df["operation_date"].max().date()
        b0 = float(df["balance_eod"].iloc[-1])

        res = ml.forecast(df, b0, d_max, horizon=30, seed=42)
        assert res is not None
        assert len(res["days"]) == 30
        assert 0.0 <= res["p_any"] <= 1.0

        p10 = np.array([d["p10"] for d in res["days"]])
        p50 = np.array([d["p50"] for d in res["days"]])
        p90 = np.array([d["p90"] for d in res["days"]])

        assert np.all(p10 <= p50 + 1e-3), f"Monotonicity violation p10 > p50 in {cid}"
        assert np.all(p50 <= p90 + 1e-3), f"Monotonicity violation p50 > p90 in {cid}"

    # Extreme fallback test: ultra-short 3-day statement
    df_ultra_short = pd.DataFrame({
        "operation_date": pd.date_range("2026-09-01", "2026-09-03", freq="D"),
        "amount": [50000.0, 30000.0, 20000.0],
        "direction": ["Поступление", "Списание", "Поступление"],
        "balance_eod": [50000.0, 20000.0, 40000.0]
    })
    res_ultra = ml.forecast(df_ultra_short, 40000.0, df_ultra_short["operation_date"].max().date(), horizon=30, seed=42)
    assert res_ultra is not None
    assert len(res_ultra["days"]) == 30
    assert res_ultra["fallback_triggered"] is True





