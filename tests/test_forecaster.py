import pandas as pd
from datetime import date
from backend.core.forecaster import ForecasterStubV01, MonteCarloForecaster

def test_forecast_contract_and_monotonicity():
    forecaster = ForecasterStubV01(k_factor=1.28)
    history = pd.DataFrame([
        {"operation_date": date(2025, 1, 1), "amount": 100000.0, "direction": "Поступление", "category_id": "cat_revenue_client", "balance_eod": 500000.0},
        {"operation_date": date(2025, 1, 2), "amount": 50000.0, "direction": "Списание", "category_id": "cat_payroll", "balance_eod": 450000.0}
    ])
    
    result = forecaster.forecast(
        history=history,
        balance_as_of=450000.0,
        as_of=date(2025, 1, 2),
        horizon=30,
        overdraft_limit=50000.0,
        seed=123
    )

    # 1. Exact horizon days
    assert len(result["days"]) == 30
    assert result["model_version"] == "stub-0.1"
    assert result["quality"] == "low"

    # 2. Monotonicity p10 <= p50 <= p90 and prob in [0, 1]
    for d in result["days"]:
        assert d["p10"] <= d["p50"], f"p10 {d['p10']} > p50 {d['p50']}"
        assert d["p50"] <= d["p90"], f"p50 {d['p50']} > p90 {d['p90']}"
        assert 0.0 <= d["prob_negative"] <= 1.0

def test_forecast_reproducibility():
    forecaster = ForecasterStubV01()
    history = pd.DataFrame([
        {"operation_date": date(2025, 1, 1), "amount": 200000.0, "direction": "Поступление", "category_id": "cat_revenue_client", "balance_eod": 300000.0}
    ])
    res1 = forecaster.forecast(history=history, balance_as_of=300000.0, as_of=date(2025, 1, 1), horizon=14, seed=42)
    res2 = forecaster.forecast(history=history, balance_as_of=300000.0, as_of=date(2025, 1, 1), horizon=14, seed=42)

    assert res1["days"][5]["p50"] == res2["days"][5]["p50"]
    assert res1["days"][5]["p10"] == res2["days"][5]["p10"]

def test_scenario_drop_revenue():
    forecaster = ForecasterStubV01()
    history = pd.DataFrame([
        {"operation_date": date(2025, 1, 1), "amount": 100000.0, "direction": "Поступление", "category_id": "cat_revenue_client", "balance_eod": 300000.0}
    ])
    baseline = forecaster.forecast(history=history, balance_as_of=300000.0, as_of=date(2025, 1, 1), horizon=10, scenario=None)
    scen = forecaster.forecast(
        history=history,
        balance_as_of=300000.0,
        as_of=date(2025, 1, 1),
        horizon=10,
        scenario={"scenario_type": "revenue_drop", "params": {"drop_percent": 30.0}}
    )
    # With revenue drop, final p50 must be lower than baseline
    assert scen["days"][-1]["p50"] <= baseline["days"][-1]["p50"]


# ===== Monte Carlo Forecaster Tests =====

def _build_mc_history():
    """Build a realistic 90-day history for Monte Carlo testing."""
    import numpy as np
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=90, freq="D")
    records = []
    balance = 1_000_000.0
    for d in dates:
        # 60% chance of inflow
        if rng.random() < 0.6:
            amt = float(rng.integers(50_000, 300_000))
            balance += amt
            records.append({
                "operation_date": d.date(),
                "amount": amt,
                "direction": "Поступление",
                "category_id": "cat_revenue_client",
                "balance_eod": balance
            })
        # 70% chance of outflow
        if rng.random() < 0.7:
            amt = float(rng.integers(10_000, 200_000))
            balance -= amt
            records.append({
                "operation_date": d.date(),
                "amount": amt,
                "direction": "Списание",
                "category_id": "cat_payroll",
                "balance_eod": balance
            })
    return pd.DataFrame(records), balance


def test_mc_forecast_contract():
    """Monte Carlo forecaster satisfies the Forecaster protocol contract."""
    mc = MonteCarloForecaster(n_simulations=500, n_sample_paths=5)
    history, balance = _build_mc_history()

    result = mc.forecast(
        history=history,
        balance_as_of=balance,
        as_of=date(2025, 3, 31),
        horizon=30,
        seed=42
    )

    assert result["model_version"] == "monte-carlo-v1.0"
    assert result["quality"] == "medium"
    assert len(result["days"]) == 30

    # Monotonicity: p10 <= p50 <= p90
    for d in result["days"]:
        assert d["p10"] <= d["p50"], f"p10 {d['p10']} > p50 {d['p50']} on {d['date']}"
        assert d["p50"] <= d["p90"], f"p50 {d['p50']} > p90 {d['p90']} on {d['date']}"
        assert 0.0 <= d["prob_negative"] <= 1.0


def test_mc_sample_paths():
    """Monte Carlo produces the correct number of sample paths."""
    mc = MonteCarloForecaster(n_simulations=500, n_sample_paths=5)
    history, balance = _build_mc_history()

    result = mc.forecast(
        history=history,
        balance_as_of=balance,
        as_of=date(2025, 3, 31),
        horizon=14,
        seed=42
    )

    assert result["sample_paths"] is not None
    assert len(result["sample_paths"]) == 5
    # Each path must have length == horizon
    for path in result["sample_paths"]:
        assert len(path) == 14


def test_mc_simulation_meta():
    """Simulation metadata contains VaR, CVaR, execution time."""
    mc = MonteCarloForecaster(n_simulations=500, n_sample_paths=5)
    history, balance = _build_mc_history()

    result = mc.forecast(
        history=history,
        balance_as_of=balance,
        as_of=date(2025, 3, 31),
        horizon=30,
        seed=42
    )

    meta = result["simulation_meta"]
    assert meta is not None
    assert meta["engine"] == "monte-carlo"
    assert meta["iterations"] == 500
    assert meta["horizon_days"] == 30
    assert meta["execution_time_ms"] > 0
    assert "var_95" in meta
    assert "cvar_95" in meta
    assert meta["var_95"] >= 0
    assert meta["cvar_95"] >= 0


def test_mc_reproducibility():
    """Same seed produces identical results."""
    mc = MonteCarloForecaster(n_simulations=500, n_sample_paths=5)
    history, balance = _build_mc_history()

    r1 = mc.forecast(history=history, balance_as_of=balance, as_of=date(2025, 3, 31), horizon=14, seed=99)
    r2 = mc.forecast(history=history, balance_as_of=balance, as_of=date(2025, 3, 31), horizon=14, seed=99)

    for d1, d2 in zip(r1["days"], r2["days"]):
        assert d1["p50"] == d2["p50"]
        assert d1["p10"] == d2["p10"]
        assert d1["p90"] == d2["p90"]


def test_mc_scenario_revenue_drop():
    """Revenue drop scenario lowers the P50 compared to baseline."""
    mc = MonteCarloForecaster(n_simulations=500, n_sample_paths=5)
    history, balance = _build_mc_history()

    baseline = mc.forecast(
        history=history, balance_as_of=balance,
        as_of=date(2025, 3, 31), horizon=30, seed=42
    )
    drop = mc.forecast(
        history=history, balance_as_of=balance,
        as_of=date(2025, 3, 31), horizon=30, seed=42,
        scenario={"scenario_type": "revenue_drop", "params": {"drop_percent": 30.0}}
    )

    # Terminal P50 should be lower with revenue drop
    assert drop["days"][-1]["p50"] < baseline["days"][-1]["p50"]
