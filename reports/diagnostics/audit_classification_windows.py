# -*- coding: utf-8 -*-
"""Diagnostic audit script for Block 5:
Evaluates classifier_model.pkl and rules on Holdout-49 (and Tune-100),
inspects all false positive windows on Holdout,
computes calibration table, Brier, ROC-AUC, PR-AUC,
and checks stability across tau in [0.1, 0.6].
"""
import sys
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import (
    confusion_matrix, brier_score_loss, roc_auc_score, average_precision_score,
    accuracy_score, precision_score, recall_score, f1_score
)
from sklearn.calibration import calibration_curve

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ML"))

# Load dataset extractor
from ML.reports.ml_jury.benchmark_classification import extract_window_dataset

print("Extracting full window dataset...")
df = extract_window_dataset()

# Load saved classifier model
model_path = ROOT / "ML" / "reports" / "ml_jury" / "classifier_model.pkl"
with open(model_path, "rb") as f:
    artifact = pickle.load(f)

scaler = artifact["scaler"]
clf = artifact["classifier"]
calibrator = artifact["calibrator"]
feature_cols = artifact["feature_cols"]
tau_star = float(artifact["threshold"])

print(f"\nLoaded classifier_model.pkl with threshold tau* = {tau_star:.3f}")
print(f"Features: {feature_cols}")

# Score all windows
X_all = scaler.transform(df[feature_cols])
raw_scores = clf.decision_function(X_all)
probs = calibrator.predict_proba(raw_scores.reshape(-1, 1))[:, 1]
df["prob_calibrated"] = probs
df["pred_label"] = (probs >= tau_star).astype(int)

# Separate Tune and Holdout
df_tune = df[df["subset"] == "tune_100"].copy()
df_holdout = df[df["subset"] == "holdout_50"].copy()

print(f"\nTune-100: {len(df_tune)} windows, {df_tune['company_id'].nunique()} companies, {df_tune['target_gap'].sum()} positive windows")
print(f"Holdout-49: {len(df_holdout)} windows, {df_holdout['company_id'].nunique()} companies, {df_holdout['target_gap'].sum()} positive windows")

# Evaluate Confusion Matrices on Holdout-49 (window level)
cm_h = confusion_matrix(df_holdout["target_gap"], df_holdout["pred_label"])
tn_h, fp_h, fn_h, tp_h = cm_h.ravel()
print(f"\nHoldout-49 Window-level Confusion Matrix (tau*={tau_star:.3f}):")
print(f"  TN={tn_h}, FP={fp_h}, FN={fn_h}, TP={tp_h}")
print(f"  Precision: {precision_score(df_holdout['target_gap'], df_holdout['pred_label'], zero_division=0):.4f}")
print(f"  Recall:    {recall_score(df_holdout['target_gap'], df_holdout['pred_label'], zero_division=0):.4f}")
print(f"  F1:        {f1_score(df_holdout['target_gap'], df_holdout['pred_label'], zero_division=0):.4f}")
print(f"  ROC-AUC:   {roc_auc_score(df_holdout['target_gap'], df_holdout['prob_calibrated']):.4f}")
print(f"  PR-AUC:    {average_precision_score(df_holdout['target_gap'], df_holdout['prob_calibrated']):.4f}")
print(f"  Brier:     {brier_score_loss(df_holdout['target_gap'], df_holdout['prob_calibrated']):.4f}")

# Company-level evaluation on Holdout-49
comp_h_true = df_holdout.groupby("company_id")["target_gap"].max()
comp_h_pred = df_holdout.groupby("company_id")["pred_label"].max()
comp_h_prob = df_holdout.groupby("company_id")["prob_calibrated"].max()

cm_comp_h = confusion_matrix(comp_h_true, comp_h_pred)
tn_ch, fp_ch, fn_ch, tp_ch = cm_comp_h.ravel()
print(f"\nHoldout-49 Company-level Confusion Matrix:")
print(f"  TN={tn_ch}, FP={fp_ch}, FN={fn_ch}, TP={tp_ch}")
print(f"  Positive companies: {comp_h_true.sum()} of {len(comp_h_true)}")

# Check threshold stability on Holdout
print("\n--- Threshold Stability on Holdout-49 (tau in [0.10, 0.60]) ---")
tau_range = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.37, 0.40, 0.45, 0.50, 0.55, 0.60]
stability_rows = []
for tau in tau_range:
    preds = (df_holdout["prob_calibrated"] >= tau).astype(int)
    cm = confusion_matrix(df_holdout["target_gap"], preds)
    tn, fp, fn, tp = cm.ravel()
    prec = precision_score(df_holdout["target_gap"], preds, zero_division=0)
    rec = recall_score(df_holdout["target_gap"], preds, zero_division=0)
    f1 = f1_score(df_holdout["target_gap"], preds, zero_division=0)
    stability_rows.append({
        "tau": tau, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "Precision": round(prec, 4), "Recall": round(rec, 4), "F1": round(f1, 4)
    })
print(pd.DataFrame(stability_rows).to_string(index=False))

# Identify all False Positive windows on Holdout across tau thresholds
print("\n--- Detailed Investigation of False Positive Windows on Holdout-49 ---")
# Check at tau* = 0.370 and at lower tau
fps_at_37 = df_holdout[(df_holdout["target_gap"] == 0) & (df_holdout["pred_label"] == 1)]
print(f"False Positives at tau* = {tau_star:.3f}: {len(fps_at_37)}")
for idx, r in fps_at_37.iterrows():
    print(f"  Company {r['company_id']}, window {r['window_idx']}, cutoff {r['cutoff_date']}: prob={r['prob_calibrated']:.4f}, init_bal={r['init_balance']:,.2f}, act_min={r['act_min_balance']:,.2f}")

# Check False Positives at tau = 0.20 and tau = 0.30
for test_tau in [0.20, 0.25, 0.30]:
    fps_sub = df_holdout[(df_holdout["target_gap"] == 0) & (df_holdout["prob_calibrated"] >= test_tau)]
    print(f"\nFalse Positives at tau = {test_tau:.2f}: {len(fps_sub)}")
    for idx, r in fps_sub.iterrows():
        # Check if this company EVER had a cash gap in any window
        comp_all_windows = df_holdout[df_holdout["company_id"] == r["company_id"]]
        had_future_gap = (comp_all_windows["target_gap"] == 1).any()
        min_ever = comp_all_windows["act_min_balance"].min()
        print(f"  Company {r['company_id']} | Window {r['window_idx']} (cutoff {r['cutoff_date']}) | prob={r['prob_calibrated']:.4f} | init_bal={r['init_balance']:,.1f} | act_min={r['act_min_balance']:,.1f} | Future Gap in other windows: {had_future_gap} (min_bal_ever: {min_ever:,.1f})")

# Also check Simulation Median Rule False Positives (P50 <= 0)
print("\n--- Simulation Median Rule (P50 <= 0) on Holdout-49 ---")
sim_pred = (df_holdout["sim_p50_min"] <= 0).astype(int)
cm_sim = confusion_matrix(df_holdout["target_gap"], sim_pred)
tn_s, fp_s, fn_s, tp_s = cm_sim.ravel()
print(f"Simulation Median Confusion Matrix: TN={tn_s}, FP={fp_s}, FN={fn_s}, TP={tp_s}")
print(f"Number of FP windows for Simulation Median Rule: {fp_s}")

# Calibration Table
print("\n--- Calibration Table for Holdout-49 ---")
bins = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
df_holdout["prob_bin"] = pd.cut(df_holdout["prob_calibrated"], bins=bins, right=False)
calib_table = df_holdout.groupby("prob_bin", observed=False).agg(
    n_windows=("target_gap", "count"),
    n_gaps=("target_gap", "sum"),
    empirical_rate=("target_gap", "mean"),
    mean_predicted_prob=("prob_calibrated", "mean")
).reset_index()
print(calib_table.to_string(index=False))

