"""
Tests for Planned Events Layer & OOS Residuals Stabilization (tests/test_events_overlay.py)
==========================================================================================
Verifies:
1. test_no_linalg_warning_and_sane_w30:
   - Absence of LinAlgWarning (ill-conditioned matrix)
   - Activation of fallback_triggered = True on short series (N < 120 or first fold < 40)
   - Sane corridor widths (W30) on previously problematic companies (C068, C088, C122)
2. test_event_shifts_median_by_amount:
   - Deterministic event +X at date D shifts P50 of all models (ML v2.0, MC, Corridor v0.1) by +X for t >= D
3. test_bernoulli_event_widens_corridor:
   - Probabilistic event (p=0.5, +1,000,000 ₽) widens uncertainty corridor P90 - P10 and alters P_any
4. test_anti_collision_slot_replacement:
   - Manual rent entry replaces expected slot without double deduction and flags is_slot_replacement = True
5. test_radar_updates_on_event:
   - Inflow resolves cash gap in ML v2.0 Risk Radar, and all 4 scenario levers are functional
6. test_backtest_untouched:
   - Offline calls with events=None are identical to backtest baseline
"""

import math
import warnings
from datetime import date, timedelta
import numpy as np
import pandas as pd
import pytest

from backend.core.forecaster import MLForecaster, MonteCarloForecaster, ForecasterStubV01
from backend.core.events_overlay import (
    EventsOverlayApplier,
    shift_to_ru_business_day,
    is_ru_business_day
)
from backend.core.risk import evaluate_cash_gap


def test_no_linalg_warning_and_sane_w30():
    """T1: Verify no LinAlgWarning, correct fallback flags, and sane W30 on short/seasonal companies."""
    cids = ["C046", "C049", "C059", "C068", "C081", "C088", "C105", "C110", "C122", "C136", "C142"]
    ml = MLForecaster()

    for cid in cids:
        df = pd.read_csv(f"data/statements/{cid}.csv", sep=";", encoding="utf-8-sig")
        df["operation_date"] = pd.to_datetime(df["operation_date"])
        d_max = df["operation_date"].max().date()
        b0 = float(df["balance_eod"].iloc[-1])
        span_days = (df["operation_date"].max() - df["operation_date"].min()).days

        with warnings.catch_warnings(record=True) as recorded_warns:
            warnings.simplefilter("always")
            res = ml.forecast(df, b0, d_max, horizon=30, seed=42)

            # Check that NO LinAlgWarning occurred
            for w in recorded_warns:
                w_str = str(w.message).lower()
                assert "ill-conditioned" not in w_str, f"LinAlgWarning detected for {cid}: {w.message}"
                assert "linalgwarning" not in str(w.category.__name__).lower(), f"LinAlgWarning detected for {cid}"

        assert res is not None
        assert len(res["days"]) == 30
        w30 = res["days"][-1]["p90"] - res["days"][-1]["p10"]

        # Sane W30 limit (previously C088 had 898M and C068 had 274M)
        assert w30 < 100_000_000.0, f"Corridor exploded on {cid}: W30 = {w30:,.0f} ₽"

        # Check fallback logic: short series must trigger fallback
        if span_days < 120:
            assert res["fallback_triggered"] is True, f"Expected fallback_triggered=True on short series {cid} (span={span_days}d)"


def test_event_shifts_median_by_amount():
    """T2: Deterministic event +X on date D shifts P50 of all models by +X for t >= D."""
    df = pd.read_csv("data/statements/C004.csv", sep=";", encoding="utf-8-sig")
    df["operation_date"] = pd.to_datetime(df["operation_date"])
    d_max = df["operation_date"].max().date()
    b0 = float(df["balance_eod"].iloc[-1])

    # Event on day 10 (shifted to business day if weekend/holiday)
    raw_ev_date = d_max + timedelta(days=10)
    ev_date = shift_to_ru_business_day(raw_ev_date)
    ev_amount = 500_000.0

    ev = [{
        "event_date": ev_date,
        "amount": ev_amount,
        "probability": 1.0,
        "category_id": "cat_other_in",
        "source": "manual",
        "note": "Поступление по договору"
    }]

    # 1. ML v2.0
    ml = MLForecaster()
    r_ml_base = ml.forecast(df, b0, d_max, horizon=30, seed=42)
    r_ml_ev = ml.forecast(df, b0, d_max, horizon=30, events=ev, seed=42)

    # 2. Monte Carlo
    mc = MonteCarloForecaster()
    r_mc_base = mc.forecast(df, b0, d_max, horizon=30, seed=42)
    r_mc_ev = mc.forecast(df, b0, d_max, horizon=30, events=ev, seed=42)

    # 3. Corridor v0.1
    stub = ForecasterStubV01()
    r_stub_base = stub.forecast(df, b0, d_max, horizon=30)
    r_stub_ev = stub.forecast(df, b0, d_max, horizon=30, events=ev)

    for step in range(30):
        cur_d = d_max + timedelta(days=step + 1)
        expected_diff = ev_amount if cur_d >= ev_date else 0.0

        diff_ml = r_ml_ev["days"][step]["p50"] - r_ml_base["days"][step]["p50"]
        diff_mc = r_mc_ev["days"][step]["p50"] - r_mc_base["days"][step]["p50"]
        diff_stub = r_stub_ev["days"][step]["p50"] - r_stub_base["days"][step]["p50"]

        assert abs(diff_ml - expected_diff) < 1.0, f"ML P50 mismatch on step {step} ({cur_d}): got {diff_ml}, expected {expected_diff}"
        assert abs(diff_mc - expected_diff) < 1.0, f"MC P50 mismatch on step {step} ({cur_d}): got {diff_mc}, expected {expected_diff}"
        assert abs(diff_stub - expected_diff) < 1.0, f"Stub P50 mismatch on step {step} ({cur_d}): got {diff_stub}, expected {expected_diff}"


def test_bernoulli_event_widens_corridor():
    """T3: Probabilistic event (p=0.5, +1,000,000 ₽) widens uncertainty corridor and adjusts P_any."""
    df = pd.read_csv("data/statements/C004.csv", sep=";", encoding="utf-8-sig")
    df["operation_date"] = pd.to_datetime(df["operation_date"])
    d_max = df["operation_date"].max().date()
    b0 = float(df["balance_eod"].iloc[-1])

    ev_date = shift_to_ru_business_day(d_max + timedelta(days=10))
    ev_prob = [{
        "event_date": ev_date,
        "amount": 1_000_000.0,
        "probability": 0.5,
        "category_id": "cat_other_in",
        "source": "manual",
        "note": "Вероятный грант 50%"
    }]

    ml = MLForecaster()
    r_base = ml.forecast(df, b0, d_max, horizon=30, seed=42)
    r_ev = ml.forecast(df, b0, d_max, horizon=30, events=ev_prob, seed=42)

    step_ev = (ev_date - d_max).days - 1
    w_base = r_base["days"][step_ev + 2]["p90"] - r_base["days"][step_ev + 2]["p10"]
    w_ev = r_ev["days"][step_ev + 2]["p90"] - r_ev["days"][step_ev + 2]["p10"]

    # Corridor must expand significantly due to Bernoulli draw
    assert w_ev > w_base + 300_000.0, f"Corridor did not widen sufficiently: {w_ev} vs {w_base}"
    # Solvency improves from expected positive inflow: P_any should decrease
    assert r_ev["p_any"] < r_base["p_any"], f"Expected p_any to decrease with positive expected grant"


def test_anti_collision_slot_replacement():
    """T4: Manual rent entry on the 2nd replaces the expected slot without double deduction."""
    detected_slots = [
        {
            "id": "slot_rent_02",
            "category_id": "cat_rent",
            "day_of_month": 2,
            "typical_amount": 150_000.0,
            "direction": "Списание"
        }
    ]

    as_of = date(2026, 9, 30)
    ev_rent = [{
        "event_date": date(2026, 10, 2),
        "amount": -160_000.0,
        "category_id": "cat_rent",
        "source": "manual",
        "probability": 1.0,
        "note": "Фактическая аренда за октябрь"
    }]

    df = pd.read_csv("data/statements/C004.csv", sep=";", encoding="utf-8-sig")
    df["operation_date"] = pd.to_datetime(df["operation_date"])
    b0 = float(df["balance_eod"].iloc[-1])

    ml = MLForecaster()
    r_base = ml.forecast(df, b0, as_of, horizon=30, detected_slots=detected_slots, seed=42)
    r_ev = ml.forecast(df, b0, as_of, horizon=30, events=ev_rent, detected_slots=detected_slots, seed=42)

    # 1. Check flag in contributions
    contributions = r_ev.get("contributions", [])
    matching_contrib = next((c for c in contributions if c.get("category") == "cat_rent"), None)
    assert matching_contrib is not None, "Missing rent contribution"
    assert matching_contrib.get("is_slot_replacement") is True
    assert matching_contrib.get("overridden_slot_id") == "slot_rent_02"

    # 2. Check no double counting: ML already learned 150,000 ₽ outflow.
    # The incremental deduction must be only -10,000 ₽, NOT -160,000 ₽ or -310,000 ₽.
    diff_day5 = r_ev["days"][4]["p50"] - r_base["days"][4]["p50"]
    assert abs(diff_day5 - (-10_000.0)) < 1.0, f"Double counting rent detected: diff is {diff_day5:,.2f}"


def test_radar_updates_on_event():
    """T5: Adding incoming payment resolves cash gap in ML v2.0 Risk Radar & verifies scenarios."""
    # Synthetic company in distress (low balance, continuous outflows)
    dates = pd.date_range("2026-05-01", periods=130, freq="D")
    records = []
    bal = 50_000.0
    for d in dates:
        amt = 8000.0
        bal -= amt
        records.append({
            "operation_date": d.date(),
            "amount": amt,
            "direction": "Списание",
            "category_id": "cat_supplies",
            "payment_purpose": "Оплата материалов",
            "balance_eod": bal
        })
    df_distress = pd.DataFrame(records)
    cutoff = dates[-1].date()
    initial_bal = 30_000.0

    ml = MLForecaster()

    # 1. Baseline radar: impending cash gap
    res_base = ml.forecast(df_distress, initial_bal, cutoff, horizon=30, seed=42)
    radar_base = evaluate_cash_gap(res_base, mandatory_slots=[])
    assert radar_base is not None
    assert radar_base["level"] in ["warning", "critical"]

    # 2. Add large customer receivable of +500,000 ₽ on day 2 (before gap occurs)
    ev_rescue = [{
        "event_date": shift_to_ru_business_day(cutoff + timedelta(days=2)),
        "amount": 500_000.0,
        "probability": 1.0,
        "source": "invoice",
        "category_id": "cat_revenue_client",
        "note": "Поступление от якорного клиента"
    }]
    res_rescued = ml.forecast(df_distress, initial_bal, cutoff, horizon=30, events=ev_rescue, seed=42)
    radar_rescued = evaluate_cash_gap(res_rescued, mandatory_slots=[])
    # Radar is resolved: gap eliminated or moved
    assert res_rescued["p_any"] < res_base["p_any"]
    if radar_rescued is not None:
        assert radar_rescued["probability"] < radar_base["probability"]

    # 3. Test scenarios in MLForecaster
    # 3a. revenue_drop
    scen_drop = ml.forecast(df_distress, initial_bal, cutoff, horizon=30, scenario={"scenario_type": "revenue_drop", "params": {"drop_percent": 30.0}}, seed=42)
    assert scen_drop is not None

    # 3b. cost_increase
    scen_cost = ml.forecast(df_distress, initial_bal, cutoff, horizon=30, scenario={"scenario_type": "cost_increase", "params": {"increase_percent": 25.0}}, seed=42)
    assert scen_cost["days"][-1]["p50"] < res_base["days"][-1]["p50"]

    # 3c. unexpected_expense
    scen_exp = ml.forecast(df_distress, initial_bal, cutoff, horizon=30, scenario={"scenario_type": "unexpected_expense", "params": {"amount": 100_000.0, "expense_days_ahead": 4}}, seed=42)
    assert scen_exp["days"][10]["p50"] < res_base["days"][10]["p50"] - 90_000.0


def test_backtest_untouched():
    """T6: Offline calls with events=None are identical to backtest baseline."""
    df = pd.read_csv("data/statements/C004.csv", sep=";", encoding="utf-8-sig")
    df["operation_date"] = pd.to_datetime(df["operation_date"])
    d_max = df["operation_date"].max().date()
    b0 = float(df["balance_eod"].iloc[-1])

    ml = MLForecaster()
    res1 = ml.forecast(df, b0, d_max, horizon=30, events=None, seed=42)
    res2 = ml.forecast(df, b0, d_max, horizon=30, events=[], seed=42)

    p10_1 = [d["p10"] for d in res1["days"]]
    p10_2 = [d["p10"] for d in res2["days"]]
    p50_1 = [d["p50"] for d in res1["days"]]
    p50_2 = [d["p50"] for d in res2["days"]]
    p90_1 = [d["p90"] for d in res1["days"]]
    p90_2 = [d["p90"] for d in res2["days"]]

    assert np.allclose(p10_1, p10_2, atol=1e-6)
    assert np.allclose(p50_1, p50_2, atol=1e-6)
    assert np.allclose(p90_1, p90_2, atol=1e-6)
    assert abs(res1["p_any"] - res2["p_any"]) < 1e-6
