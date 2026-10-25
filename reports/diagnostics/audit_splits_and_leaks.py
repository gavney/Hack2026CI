# -*- coding: utf-8 -*-
import sys
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent

print("=== AUDIT BLOCK 2: Data Leaks and Splits ===")

# 1. Statements directory
statements_dir = ROOT / "ML" / "statements"
if not statements_dir.exists():
    statements_dir = ROOT / "data" / "statements"

files = sorted(statements_dir.glob("C*.csv"))
all_cids = [f.stem for f in files]
print(f"Total company files found: {len(all_cids)} (first: {all_cids[0]}, last: {all_cids[-1]})")

tune_cids_bench = all_cids[:100]
holdout_cids_bench = all_cids[100:]
print(f"Benchmark split (by index): Tune-100 = {len(tune_cids_bench)}, Holdout = {len(holdout_cids_bench)}")

# Check c1_company_split.json
split_json_path = ROOT / "ML" / "reports" / "c1_company_split.json"
if split_json_path.exists():
    with open(split_json_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)
    print("Keys in c1_company_split.json:", list(split_data.keys()))
    if "splits" in split_data or "train_tune" in split_data:
        train_tune = split_data.get("train_tune", split_data.get("splits", {}).get("train_tune", []))
        holdout = split_data.get("holdout_test", split_data.get("splits", {}).get("holdout_test", []))
        print(f"c1_company_split.json: train_tune count = {len(train_tune)}, holdout count = {len(holdout)}")
        
        # Check overlap
        overlap = set(train_tune).intersection(set(holdout))
        print(f"Overlap between train_tune and holdout: {overlap}")
        
        # Compare with bench split
        print(f"Are train_tune exactly all_cids[:100]? {set(train_tune) == set(tune_cids_bench)}")
        diff_tune = set(tune_cids_bench).symmetric_difference(set(train_tune))
        print(f"Symmetric difference in tune: {len(diff_tune)} companies: {list(diff_tune)[:10]}")
else:
    print("c1_company_split.json NOT FOUND")

# 2. Check classifier training in save_trained_classifier.py
stc_path = ROOT / "ML" / "reports" / "ml_jury" / "save_trained_classifier.py"
stc_content = stc_path.read_text(encoding="utf-8")
print("\nChecking save_trained_classifier.py:")
print("Uses subset == 'tune_100':", "subset == \"tune_100\"" in stc_content)
print("Fits calibrator on:", "calibrator.fit(tune_oof_raw_scores.reshape(-1, 1), df_tune[\"target_gap\"].values)" in stc_content)
print("Finds tau* on:", "oof_probs >= tau" in stc_content)

# 3. Check had_past_gap and feature calculations
bench_cls_path = ROOT / "ML" / "reports" / "ml_jury" / "benchmark_classification.py"
bench_text = bench_cls_path.read_text(encoding="utf-8")
print("\nChecking benchmark_classification.py feature bounds:")
lines = bench_text.splitlines()
for i, l in enumerate(lines):
    if "train_flows = flows[:start]" in l or "train_balances = balances[:start]" in l:
        print(f"L{i+1}: {l.strip()}")
    if "had_past_gap =" in l:
        print(f"L{i+1}: {l.strip()}")
    if "target_gap =" in l:
        print(f"L{i+1}: {l.strip()}")

