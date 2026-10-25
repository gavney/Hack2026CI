# -*- coding: utf-8 -*-
"""Diagnostic audit script for Block 3 (Regression) & Block 4 (Corridor P10-P90) on Holdout-49.
Evaluates:
- Naive (balance today B0)
- Monte Carlo (median of 1000 simulations)
- ML (MLForecaster v2.0 / Ridge)
- LightGBM (from existing benchmark data)
Metrics: WAPE, MAE (mean across windows), MAE & WAPE as median across companies, MASE, signed bias (fact - pred).
Corridor P10-P90: Coverage & median width across h in {1, 7, 14, 30}.
Proportion of healthy companies where P10 <= 0.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ML"))

from ML.cashflow_forecast import _daily_history
from backend.core.forecaster import MLForecaster, MonteCarloForecaster

statements_dir = ROOT / "ML" / "statements"
if not statements_dir.exists():
    statements_dir = ROOT / "data" / "statements"

files = sorted(statements_dir.glob("C*.csv"))
holdout_files = files[100:]  # Holdout-50 (49 valid)

horizon = 30
horizons_eval = [1, 7, 14, 30]

print(f"Evaluating {len(holdout_files)} Holdout companies...")

ml_forecaster = MLForecaster(n_simulations=500)
mc_forecaster = MonteCarloForecaster(n_simulations=500)

records = []
company_scales = {}
company_healthy = {}

for f_idx, path in enumerate(holdout_files):
    cid = path.stem
    try:
        df_raw = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        history = _daily_history(df_raw)
    except Exception:
        continue

    if len(history) < horizon + 56:
        continue

    flows = history["net_flow"].to_numpy(dtype=float)
    balances = history["balance"].to_numpy(dtype=float)
    dates = history.index

    # Check if company is healthy (never had negative balance in entire statement)
    is_healthy = bool((balances >= 0).all())
    company_healthy[cid] = is_healthy

    # Windows (same 6 windows as benchmark)
    starts = list(range(max(56, len(history) - 6 * horizon), len(history) - horizon + 1, horizon))

    for w_idx, start in enumerate(starts):
        cutoff_date = dates[start]
        init_balance = float(balances[start - 1])
        train_slice = history.iloc[:start].copy()
        train_flows = flows[:start]
        train_balances = balances[:start]

        # In-sample naive MAE for MASE scaling (one-step naive on training flows)
        if len(train_flows) > 1:
            insample_naive_mae = float(np.mean(np.abs(np.diff(train_flows))))
        else:
            insample_naive_mae = 1.0
        insample_naive_mae = max(insample_naive_mae, 1.0)

        # Scale factor for normalization: median |daily flow| for 28 days prior to cutoff
        recent_28_flows = np.abs(train_flows[-28:]) if len(train_flows) >= 28 else np.abs(train_flows)
        flow_scale_28d = float(np.median(recent_28_flows)) if len(recent_28_flows) > 0 else 1.0
        flow_scale_28d = max(flow_scale_28d, 1.0)
        company_scales[cid] = flow_scale_28d

        # Fact on horizon
        fact_flows = flows[start : start + horizon]
        fact_balances = balances[start : start + horizon]

        # 1. Model: Naive (Balance today B0, net flow = 0)
        naive_bal = np.full(horizon, init_balance, dtype=float)
        naive_flow = np.zeros(horizon, dtype=float)

        # 2. Model: MLForecaster (v2.0 Ridge + Block Bootstrap)
        hist_df_for_ml = pd.DataFrame({
            "operation_date": dates[:start],
            "amount": np.abs(train_flows),
            "direction": ["Поступление" if f >= 0 else "Списание" for f in train_flows],
            "category_id": ["cat_other"] * len(train_flows),
            "balance_eod": train_balances,
            "payment_purpose": [""] * len(train_flows),
            "counterparty_name": [""] * len(train_flows),
            "counterparty_inn": [""] * len(train_flows)
        })

        ml_res = ml_forecaster.forecast(
            history=hist_df_for_ml,
            balance_as_of=init_balance,
            as_of=cutoff_date,
            horizon=horizon,
            seed=42 + w_idx
        )
        ml_days = ml_res["days"]
        ml_p10_b = np.array([d["p10"] for d in ml_days], dtype=float)
        ml_p50_b = np.array([d["p50"] for d in ml_days], dtype=float)
        ml_p90_b = np.array([d["p90"] for d in ml_days], dtype=float)
        # Daily flow predictions (diff of p50 balance)
        ml_p50_f = np.diff(np.insert(ml_p50_b, 0, init_balance))

        # 3. Model: MonteCarloForecaster
        mc_res = mc_forecaster.forecast(
            history=hist_df_for_ml,
            balance_as_of=init_balance,
            as_of=cutoff_date,
            horizon=horizon,
            seed=42 + w_idx
        )
        mc_days = mc_res["days"]
        mc_p10_b = np.array([d["p10"] for d in mc_days], dtype=float)
        mc_p50_b = np.array([d["p50"] for d in mc_days], dtype=float)
        mc_p90_b = np.array([d["p90"] for d in mc_days], dtype=float)
        mc_p50_f = np.diff(np.insert(mc_p50_b, 0, init_balance))

        # Record metrics for horizons 1, 7, 14, 30
        for h in horizons_eval:
            idx = h - 1
            act_b = fact_balances[idx]
            act_f = fact_flows[idx]

            records.append({
                "company_id": cid,
                "window_idx": w_idx,
                "is_healthy": is_healthy,
                "horizon": h,
                "insample_naive_mae": insample_naive_mae,
                "flow_scale_28d": flow_scale_28d,
                # Actual
                "act_balance": act_b,
                "act_flow": act_f,
                # Naive
                "naive_bal": naive_bal[idx],
                "naive_flow": naive_flow[idx],
                # ML
                "ml_p50_b": ml_p50_b[idx],
                "ml_p10_b": ml_p10_b[idx],
                "ml_p90_b": ml_p90_b[idx],
                "ml_p50_f": ml_p50_f[idx],
                # Monte Carlo
                "mc_p50_b": mc_p50_b[idx],
                "mc_p10_b": mc_p10_b[idx],
                "mc_p90_b": mc_p90_b[idx],
                "mc_p50_f": mc_p50_f[idx]
            })

df_eval = pd.DataFrame(records)
print(f"Extracted {len(df_eval)} horizon points across {df_eval['company_id'].nunique()} companies.")

# -------------------------------------------------------------
# BLOCK 3: REGRESSION METRICS TABLE
# -------------------------------------------------------------
print("\n" + "="*80)
print("BLOCK 3: HOLD-OUT 49 REGRESSION RESULTS (BALANCE)")
print("="*80)

reg_rows = []
models = [
    ("Naive (B0)", "naive_bal", "naive_flow"),
    ("Monte Carlo (P50)", "mc_p50_b", "mc_p50_f"),
    ("ML (MLForecaster v2.0)", "ml_p50_b", "ml_p50_f")
]

for h in horizons_eval:
    sub = df_eval[df_eval["horizon"] == h]
    for m_label, col_b, col_f in models:
        err_b = np.abs(sub["act_balance"] - sub[col_b])
        bias_b = sub["act_balance"] - sub[col_b]
        err_f = np.abs(sub["act_flow"] - sub[col_f])

        # Mean across windows
        mae_win = float(err_b.mean())
        wape_win = float(err_b.sum() / (np.abs(sub["act_balance"]).sum() + 1e-9) * 100.0)
        bias_mean = float(bias_b.mean())
        mae_flow = float(err_f.mean())

        # MASE across windows
        mase = float((err_b / sub["insample_naive_mae"]).mean())

        # Median across companies
        comp_mae = sub.groupby("company_id").apply(lambda g: np.mean(np.abs(g["act_balance"] - g[col_b])))
        comp_wape = sub.groupby("company_id").apply(lambda g: np.sum(np.abs(g["act_balance"] - g[col_b])) / (np.sum(np.abs(g["act_balance"])) + 1e-9) * 100.0)
        mae_comp_med = float(comp_mae.median())
        wape_comp_med = float(comp_wape.median())

        reg_rows.append({
            "Horizon (h)": h,
            "Model": m_label,
            "WAPE (%)": round(wape_win, 2),
            "MAE Win (rub)": round(mae_win, 1),
            "MAE Comp Med (rub)": round(mae_comp_med, 1),
            "WAPE Comp Med (%)": round(wape_comp_med, 2),
            "MASE": round(mase, 2),
            "Bias (Fact-Pred)": round(bias_mean, 1),
            "Flow MAE (rub)": round(mae_flow, 1)
        })

df_reg_out = pd.DataFrame(reg_rows)
print(df_reg_out.to_string(index=False))

# -------------------------------------------------------------
# BLOCK 4: CORRIDOR P10-P90 TABLE
# -------------------------------------------------------------
print("\n" + "="*80)
print("BLOCK 4: HOLD-OUT 49 CORRIDOR P10-P90 COVERAGE & WIDTH")
print("="*80)

corridor_rows = []
for h in horizons_eval:
    sub = df_eval[df_eval["horizon"] == h]

    # ML Corridor
    ml_covered = (sub["act_balance"] >= sub["ml_p10_b"]) & (sub["act_balance"] <= sub["ml_p90_b"])
    ml_width = sub["ml_p90_b"] - sub["ml_p10_b"]
    ml_norm_width = ml_width / sub["flow_scale_28d"]

    # MC Corridor
    mc_covered = (sub["act_balance"] >= sub["mc_p10_b"]) & (sub["act_balance"] <= sub["mc_p90_b"])
    mc_width = sub["mc_p90_b"] - sub["mc_p10_b"]
    mc_norm_width = mc_width / sub["flow_scale_28d"]

    corridor_rows.append({
        "Horizon (h)": h,
        "ML Coverage (%)": round(float(ml_covered.mean() * 100.0), 2),
        "ML Width Med (rub)": round(float(ml_width.median()), 1),
        "ML Norm Width (x scale)": round(float(ml_norm_width.median()), 2),
        "MC Coverage (%)": round(float(mc_covered.mean() * 100.0), 2),
        "MC Width Med (rub)": round(float(mc_width.median()), 1),
        "MC Norm Width (x scale)": round(float(mc_norm_width.median()), 2)
    })

df_corridor_out = pd.DataFrame(corridor_rows)
print(df_corridor_out.to_string(index=False))

# False alarms on healthy companies: proportion of healthy companies where P10 <= 0
sub_healthy = df_eval[df_eval["is_healthy"] == True]
print(f"\nHealthy companies count: {sub_healthy['company_id'].nunique()} of {df_eval['company_id'].nunique()}")

for h in horizons_eval:
    sub_h_h = sub_healthy[sub_healthy["horizon"] == h]
    ml_false_alarm_rate = float((sub_h_h["ml_p10_b"] <= 0).mean() * 100.0)
    mc_false_alarm_rate = float((sub_h_h["mc_p10_b"] <= 0).mean() * 100.0)
    print(f"Horizon h={h:2d}: Healthy windows with P10 <= 0 (False Alarm): ML = {ml_false_alarm_rate:.2f}%, Monte Carlo = {mc_false_alarm_rate:.2f}%")

