# -*- coding: utf-8 -*-
"""Diagnostic audit script for Block 7 (Overfitting) & Block 8 (Data Quality).
Analyzes:
1. Balance distribution across all 150 companies (min, median, max).
2. Missing dates, duplicate dates, history < 120 days across all 150 companies.
3. Top-5 companies share in total MAE on Holdout.
4. Overfitting: Tune OOF vs Holdout error across models.
5. LightGBM learning curve inspection.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ML"))

statements_dir = ROOT / "ML" / "statements"
if not statements_dir.exists():
    statements_dir = ROOT / "data" / "statements"

files = sorted(statements_dir.glob("C*.csv"))
print(f"Total statement files: {len(files)}")

# 1. Statements Data Quality Audit
records = []
all_balances = []
all_turnovers = []

short_history_cids = []
missing_dates_info = []
duplicate_dates_info = []

for p in files:
    cid = p.stem
    df = pd.read_csv(p, sep=";", encoding="utf-8-sig")
    
    # Check required columns
    date_col = next((c for c in df.columns if any(k in c.lower() for k in ["дата", "date"])), None)
    bal_col = next((c for c in df.columns if any(k in c.lower() for k in ["остаток", "balance", "eod"])), None)
    amt_col = next((c for c in df.columns if any(k in c.lower() for k in ["сумма", "amount"])), None)
    dir_col = next((c for c in df.columns if any(k in c.lower() for k in ["direction", "направление", "тип"])), None)
    
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    
    # Check duplicates in raw operations
    dup_count = df.duplicated(subset=[date_col, amt_col, dir_col]).sum()
    if dup_count > 0:
        duplicate_dates_info.append((cid, int(dup_count)))
        
    # Aggregate daily
    daily_dates = df[date_col].dt.floor("D")
    unique_dates = pd.date_range(daily_dates.min(), daily_dates.max(), freq="D")
    actual_dates = daily_dates.unique()
    missing_days = len(unique_dates) - len(actual_dates)
    if missing_days > 0:
        missing_dates_info.append((cid, missing_days, len(unique_dates)))
        
    n_days_span = (daily_dates.max() - daily_dates.min()).days + 1
    if n_days_span < 120 or len(actual_dates) < 120:
        short_history_cids.append((cid, len(actual_dates), n_days_span))
        
    bals = df[bal_col].dropna().values
    if len(bals) > 0:
        min_b = float(np.min(bals))
        med_b = float(np.median(bals))
        max_b = float(np.max(bals))
        all_balances.extend(bals)
    else:
        min_b, med_b, max_b = 0.0, 0.0, 0.0
        
    records.append({
        "company_id": cid,
        "n_ops": len(df),
        "n_unique_days": len(actual_dates),
        "days_span": n_days_span,
        "missing_calendar_days": missing_days,
        "min_balance": min_b,
        "median_balance": med_b,
        "max_balance": max_b,
        "has_gap": bool(min_b < 0.0),
        "has_zero": bool(min_b == 0.0)
    })

df_audit = pd.DataFrame(records)

print("\n" + "="*80)
print("BLOCK 8: DATA QUALITY AUDIT (150 COMPANIES)")
print("="*80)
print(f"Total companies analyzed: {len(df_audit)}")
print(f"Companies with short history (< 120 unique days): {len(short_history_cids)}")
for c, u, s in short_history_cids:
    print(f"  {c}: unique_days={u}, days_span={s}")

print(f"\nCompanies with missing calendar days in range [start_date, end_date]: {len(missing_dates_info)}")
print(f"  (Note: weekend/holiday bank non-working days where no operations occurred)")
if missing_dates_info:
    tot_missing = sum(m[1] for m in missing_dates_info)
    print(f"  Total missing calendar date gaps: {tot_missing} days across {len(missing_dates_info)} companies")
    print(f"  Example first 5: {missing_dates_info[:5]}")

print(f"\nCompanies with raw operation duplicates: {len(duplicate_dates_info)}")
if duplicate_dates_info:
    print(f"  Duplicates list: {duplicate_dates_info}")

print("\nBalance Distribution across entire portfolio (all operations):")
print(f"  Global Min Balance:    {float(np.min(all_balances)):,.2f} руб.")
print(f"  Global 10th percentile:{float(np.percentile(all_balances, 10)):,.2f} руб.")
print(f"  Global Median Balance: {float(np.median(all_balances)):,.2f} руб.")
print(f"  Global 90th percentile:{float(np.percentile(all_balances, 90)):,.2f} руб.")
print(f"  Global Max Balance:    {float(np.max(all_balances)):,.2f} руб.")

print("\nCompany-level Median Balance Distribution:")
print(f"  Min of company medians:    {df_audit['median_balance'].min():,.2f} руб.")
print(f"  Median of company medians: {df_audit['median_balance'].median():,.2f} руб.")
print(f"  Max of company medians:    {df_audit['median_balance'].max():,.2f} руб.")

print(f"\nCompanies with strictly negative balance (min < 0): {df_audit['has_gap'].sum()} of {len(df_audit)}")
gap_cids = df_audit[df_audit["has_gap"]]["company_id"].tolist()
print(f"  Gap company IDs: {gap_cids}")
print(f"Companies with minimum balance == 0.0: {df_audit['has_zero'].sum()} of {len(df_audit)}")
zero_cids = df_audit[df_audit["has_zero"]]["company_id"].tolist()
print(f"  Zero min balance IDs: {zero_cids}")

# 2. Check Top-5 Companies share in MAE
print("\n" + "="*80)
print("BLOCK 8: TOP-5 COMPANIES SHARE IN TOTAL MAE (HOLDOUT-49)")
print("="*80)

# Check from existing regression metrics or distributions
reg_dist_path = ROOT / "ML" / "reports" / "ml_jury" / "regression_company_distributions.csv"
if reg_dist_path.exists():
    df_dist = pd.read_csv(reg_dist_path, sep=";")
    print("Found regression_company_distributions.csv")

