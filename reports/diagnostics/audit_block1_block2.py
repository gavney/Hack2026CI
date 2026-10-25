# -*- coding: utf-8 -*-
import sys
import pickle
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ML"))

print("=== AUDIT BLOCK 1: Artifact Consistency ===")

# 1. Inspect classifier_model.pkl
model_path = ROOT / "ML" / "reports" / "ml_jury" / "classifier_model.pkl"
print(f"Checking {model_path}...")
if model_path.exists():
    with open(model_path, "rb") as f:
        artifact = pickle.load(f)
    print("Keys in artifact:", list(artifact.keys()))
    print("Features:", artifact.get("feature_cols"))
    print("Threshold tau*:", artifact.get("threshold"))
    print("Base rate tune:", artifact.get("base_rate_tune"))
    print("Classifier type:", type(artifact.get("classifier")))
    print("Classifier classes:", getattr(artifact.get("classifier"), "classes_", None))
    print("Classifier coef:", getattr(artifact.get("classifier"), "coef_", None))
    print("Calibrator type:", type(artifact.get("calibrator")))
    print("Calibrator coef:", getattr(artifact.get("calibrator"), "coef_", None))
else:
    print("classifier_model.pkl NOT FOUND!")

# Check if classifier_model.pkl exists in backend/ or other places
all_pkls = list(ROOT.glob("**/classifier_model.pkl"))
print("All classifier_model.pkl locations in project:", [str(p.relative_to(ROOT)) for p in all_pkls])

# Check references in backend
backend_files = list((ROOT / "backend").glob("**/*.py"))
backend_refs = []
for bf in backend_files:
    text = bf.read_text(encoding="utf-8", errors="ignore")
    if "classifier_model" in text:
        backend_refs.append(str(bf.relative_to(ROOT)))
print("Backend references to classifier_model:", backend_refs)

# Check label and tau* in scripts
scripts_to_check = [
    ROOT / "ML" / "reports" / "ml_jury" / "save_trained_classifier.py",
    ROOT / "ML" / "reports" / "ml_jury" / "benchmark_classification.py",
    ROOT / "ML" / "reports" / "ml_jury" / "benchmark_lightgbm.py",
    ROOT / "ML" / "reports" / "ml_jury" / "benchmark_regression.py",
    ROOT / "ML" / "run_control.py",
    ROOT / "backend" / "core" / "forecaster.py",
    ROOT / "backend" / "routers" / "forecast.py"
]

print("\n--- Script Label & Tau* Inspection ---")
for s in scripts_to_check:
    if not s.exists():
        print(f"File {s.name}: NOT FOUND")
        continue
    content = s.read_text(encoding="utf-8", errors="ignore")
    
    # Check gap label condition
    labels = []
    if "<= 0" in content: labels.append("<= 0")
    if "< 0" in content: labels.append("< 0")
    if "< -0.01" in content: labels.append("< -0.01")
    if "<= -0.01" in content: labels.append("<= -0.01")
    
    # Check tau* or threshold
    tau_info = []
    for line_no, line in enumerate(content.splitlines(), 1):
        if any(k in line.lower() for k in ["tau", "threshold = 0.", "threshold: float = 0."]):
            if not line.strip().startswith("#"):
                tau_info.append(f"L{line_no}: {line.strip()[:70]}")
    
    print(f"\n{s.relative_to(ROOT)}:")
    print(f"  Gap conditions found: {set(labels)}")
    print(f"  Tau lines (first 3): {tau_info[:3]}")

