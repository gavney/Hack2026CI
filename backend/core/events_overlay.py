"""
Events Overlay Applier Module (backend/core/events_overlay.py)
==============================================================
Provides a unified, deterministic and probabilistic overlay of planned user events,
invoices, contracts, taxes, and 'what-if' scenarios across ALL forecasting models:
- MLForecaster (ML v2.0)
- MonteCarloForecaster
- ForecasterStubV01 (Corridor v0.1)
- Step1Forecaster
- OldMLForecaster

Key Features:
1. Calendar shifts: Weekend and Russian official holidays shifted to the next business day.
2. Deduplication / Anti-Collision: Prevents double-counting of recurring slots.
   - For ML models: detected slots are already learned in training flow; if a user event
     collides with a slot, only the incremental delta (event.amount - slot.amount) is applied.
   - For Monte Carlo: user event replaces the slot completely.
3. Bernoulli sampling for probabilistic events (0 < p < 1) in trajectory models:
   Each trajectory draws an indicator Bernoulli(p), preserving multimodal uncertainty.
4. Analytical mixture-of-Gaussians for non-trajectory models (ForecasterStubV01):
   Mean shifts by p * amount, variance increases by p*(1-p)*amount^2.
5. Scenario levers:
   - revenue_drop: scales inflows by (1 - drop_pct)
   - cost_increase: scales outflows by (1 + inc_pct)
   - delayed_payment: shifts inflows by delay_days
   - unexpected_expense: injects one-off expense on target date
6. Zero leakage into offline backtests: backtests call models without external events.
"""

from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
import math
import numpy as np
import pandas as pd
from scipy.stats import norm

# --- Russian Official Calendar (Art. 112 Labor Code RF) ---
RU_HOLIDAYS_FIXED = {
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),  # New Year holidays
    (2, 23),  # Defender of the Fatherland Day
    (3, 8),   # International Women's Day
    (5, 1),   # Spring and Labor Day
    (5, 9),   # Victory Day
    (6, 12),  # Russia Day
    (11, 4)   # Unity Day
}


def is_ru_business_day(d: date) -> bool:
    """Checks whether date d is a working day (excluding weekends and official Russian holidays)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if (d.month, d.day) in RU_HOLIDAYS_FIXED:
        return False
    return True


def shift_to_ru_business_day(d: date) -> date:
    """Shifts date forward to the nearest Russian business day."""
    cur = d
    while not is_ru_business_day(cur):
        cur = cur + timedelta(days=1)
    return cur


def check_slot_collision(
    event_date: date,
    event_amount: float,
    event_category: Optional[str],
    event_source: str,
    detected_slots: List[Dict[str, Any]],
    as_of: date,
    horizon: int
) -> Tuple[bool, Optional[str], float]:
    """
    Checks if a user event collides with an auto-detected recurring slot.
    Criteria:
      - source != 'slot'
      - Same category (or both are regular outflows)
      - Date is within +/- 3 days of expected slot date (after business day shift)
      - Amount is within +/- 20% of slot's typical median amount
    Returns:
      (is_collision, overridden_slot_id, slot_signed_typical_amount)
    """
    if event_source == "slot":
        return False, None, 0.0

    if not detected_slots:
        return False, None, 0.0

    ev_amt_abs = abs(event_amount)
    ev_direction = "Поступление" if event_amount > 0 else "Списание"

    # Evaluate across months in horizon
    start_d = as_of + timedelta(days=1)
    end_d = as_of + timedelta(days=horizon)

    for slot in detected_slots:
        slot_cat = slot.get("category_id")
        slot_day = int(slot.get("day_of_month", 1))
        slot_amt = float(slot.get("typical_amount", 0.0))
        slot_dir = slot.get("direction", "Списание")
        slot_signed = slot_amt if slot_dir == "Поступление" else -slot_amt

        # Category or direction match
        cat_match = (event_category and slot_cat and event_category == slot_cat)
        dir_match = (ev_direction == slot_dir)
        if not (cat_match or (not event_category and dir_match)):
            continue

        # Amount check within +/- 20%
        if slot_amt > 0:
            diff_ratio = abs(ev_amt_abs - slot_amt) / slot_amt
            if diff_ratio > 0.20:
                continue
        else:
            continue

        # Check candidate dates for this slot across months
        cur_y = start_d.year
        cur_m = start_d.month
        while True:
            try:
                # determine days in month
                if cur_m in (4, 6, 9, 11):
                    max_d = 30
                elif cur_m == 2:
                    is_leap = (cur_y % 4 == 0 and cur_y % 100 != 0) or (cur_y % 400 == 0)
                    max_d = 29 if is_leap else 28
                else:
                    max_d = 31

                cand_d = date(cur_y, cur_m, min(slot_day, max_d))
                shifted_d = shift_to_ru_business_day(cand_d)

                if shifted_d > end_d + timedelta(days=7):
                    break

                if abs((event_date - shifted_d).days) <= 3:
                    slot_id = slot.get("id") or f"{slot_cat}_{slot_day}"
                    return True, str(slot_id), slot_signed
            except ValueError:
                pass

            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1

    return False, None, 0.0


class EventsOverlayApplier:
    """
    Unified Planned Events Layer.
    Applies deterministic and probabilistic events onto any forecasting model.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def prepare_events(
        self,
        events: Optional[List[Dict[str, Any]]],
        detected_slots: Optional[List[Dict[str, Any]]],
        as_of: date,
        horizon: int,
        scenario: Optional[Dict[str, Any]] = None,
        is_ml: bool = True,
        slots_as_events: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Normalizes, filters, shifts, deduplicates and applies scenario levers to events.
        """
        if events is None:
            raw_events = []
        else:
            raw_events = [dict(ev) for ev in events]

        detected_slots = detected_slots or []

        # 1. Parse scenario levers
        scenario_type = scenario.get("scenario_type") if scenario else None
        scenario_params = scenario.get("params", {}) if scenario else {}
        drop_pct = float(scenario_params.get("drop_percent", 20.0)) / 100.0 if scenario_type == "revenue_drop" else 0.0
        inc_pct = float(scenario_params.get("increase_percent", 15.0)) / 100.0 if scenario_type == "cost_increase" else 0.0
        delay_days = int(scenario_params.get("delay_days", 14)) if scenario_type == "delayed_payment" else 0

        # Inject unexpected_expense scenario event if present
        if scenario_type == "unexpected_expense":
            exp_amount = float(scenario_params.get("amount", 250000.0))
            exp_days = int(scenario_params.get("expense_days_ahead", 5))
            target_d = as_of + timedelta(days=exp_days)
            raw_events.append({
                "event_date": target_d,
                "amount": -abs(exp_amount),
                "probability": 1.0,
                "category_id": "cat_other",
                "source": "scenario",
                "note": "Внеплановый крупный расход (сценарий)"
            })

        processed = []
        for ev in raw_events:
            # Parse date
            raw_d = ev.get("event_date")
            if isinstance(raw_d, str):
                d_obj = pd.to_datetime(raw_d).date()
            elif isinstance(raw_d, (datetime_obj := (pd.Timestamp, date))):
                d_obj = raw_d if isinstance(raw_d, date) else raw_d.date()
            else:
                continue

            src = str(ev.get("source", "manual"))
            amt = float(ev.get("amount", 0.0))
            prob = float(ev.get("probability", 1.0))
            prob = max(0.0, min(1.0, prob))
            cat = ev.get("category_id") or ("cat_revenue_client" if amt > 0 else "cat_other")

            # Check collision with detected recurring slots
            is_collision, overridden_id, slot_median = check_slot_collision(
                event_date=d_obj,
                event_amount=amt,
                event_category=cat,
                event_source=src,
                detected_slots=detected_slots,
                as_of=as_of,
                horizon=horizon
            )

            # Include all slots and events in ML and MC alike
            # (unless duplicate collision handling is active)

            eff_amt = amt
            if is_collision:
                if is_ml:
                    # In ML, regular slot is already in the baseline; only add the delta
                    eff_amt = amt - slot_median
                else:
                    # In Monte Carlo, replace slot with full event amount
                    eff_amt = amt

            # Apply scenario adjustments
            eff_d = d_obj
            if scenario_type == "delayed_payment" and eff_amt > 0:
                eff_d = eff_d + timedelta(days=delay_days)

            if scenario_type == "revenue_drop" and eff_amt > 0:
                eff_amt *= max(0.0, 1.0 - drop_pct)

            if scenario_type == "cost_increase" and eff_amt < 0:
                eff_amt *= (1.0 + inc_pct)

            # Shift to Russian business banking day
            eff_d = shift_to_ru_business_day(eff_d)

            # Check if within horizon
            if not (as_of < eff_d <= as_of + timedelta(days=horizon)):
                continue

            processed.append({
                "original_date": d_obj,
                "event_date": eff_d,
                "original_amount": amt,
                "amount": eff_amt,
                "probability": prob,
                "category_id": cat or "cat_other",
                "source": src,
                "note": ev.get("note", ""),
                "is_slot_replacement": is_collision,
                "overridden_slot_id": overridden_id
            })

        return processed

    def apply_to_trajectories(
        self,
        paths: np.ndarray,
        base_p50: np.ndarray,
        events: Optional[List[Dict[str, Any]]],
        detected_slots: Optional[List[Dict[str, Any]]],
        as_of: date,
        horizon: int,
        overdraft_limit: float = 0.0,
        scenario: Optional[Dict[str, Any]] = None,
        is_ml: bool = True,
        slots_as_events: bool = True,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Applies prepared events to an ensemble of trajectories (paths of shape (n_sims, horizon)).
        - Deterministic events (p=1.0) shift all trajectories and base_p50.
        - Probabilistic events (0 < p < 1.0) draw Bernoulli(p) indicators per trajectory.
        """
        rng_seed = seed if seed is not None else self.seed
        prep_events = self.prepare_events(
            events=events,
            detected_slots=detected_slots,
            as_of=as_of,
            horizon=horizon,
            scenario=scenario,
            is_ml=is_ml,
            slots_as_events=slots_as_events
        )

        n_sims, h_len = paths.shape
        updated_paths = paths.copy()
        updated_p50 = base_p50.copy()

        contributions: List[Dict[str, Any]] = []

        for ev_idx, ev in enumerate(prep_events):
            ev_d = ev["event_date"]
            step_idx = (ev_d - as_of).days - 1
            if not (0 <= step_idx < h_len):
                continue

            amt = ev["amount"]
            prob = ev["probability"]

            if prob >= 1.0:
                # Deterministic shift on all trajectories
                updated_paths[:, step_idx:] += amt
                updated_p50[step_idx:] += amt
            elif prob > 0.0:
                # Bernoulli draw per trajectory (vectorized)
                rng = np.random.default_rng(rng_seed + ev_idx * 137 + 17)
                bern_mask = rng.uniform(0.0, 1.0, size=n_sims) < prob
                updated_paths[bern_mask, step_idx:] += amt
                # Expected mean shift on median
                updated_p50[step_idx:] += prob * amt

            if True:  # Include all events in contributions
                contributions.append({
                    "date": ev_d,
                    "category": ev["category_id"],
                    "amount": round(amt, 2),
                    "probability": round(prob, 2),
                    "source": ev["source"],
                    "is_slot_replacement": ev["is_slot_replacement"],
                    "overridden_slot_id": ev["overridden_slot_id"]
                })

        # Recalculate percentiles
        p10_arr = np.percentile(updated_paths, 10, axis=0)
        p50_arr = updated_p50
        p90_arr = np.percentile(updated_paths, 90, axis=0)

        # Monotonicity Guarantee
        p10_arr = np.minimum(p10_arr, p50_arr)
        p90_arr = np.maximum(p90_arr, p50_arr)

        effective_threshold = -float(overdraft_limit)
        prob_neg_arr = np.mean(updated_paths < effective_threshold, axis=0)
        min_balances_sim = np.min(updated_paths, axis=1)
        p_any = float(np.mean(min_balances_sim < effective_threshold))

        return {
            "paths": updated_paths,
            "p10": p10_arr,
            "p50": p50_arr,
            "p90": p90_arr,
            "prob_negative": prob_neg_arr,
            "p_any": p_any,
            "contributions": contributions,
            "processed_events": prep_events
        }

    def apply_to_analytical(
        self,
        p10_arr: np.ndarray,
        p50_arr: np.ndarray,
        p90_arr: np.ndarray,
        p_any: float,
        events: Optional[List[Dict[str, Any]]],
        detected_slots: Optional[List[Dict[str, Any]]],
        as_of: date,
        horizon: int,
        overdraft_limit: float = 0.0,
        scenario: Optional[Dict[str, Any]] = None,
        k_factor: float = 1.28155,
        is_ml: bool = False
    ) -> Dict[str, Any]:
        """
        Applies prepared events to an analytical model (without trajectories, e.g. ForecasterStubV01).
        - Deterministic events (p=1.0) shift p10, p50, p90 equally.
        - Probabilistic events (0 < p < 1.0) use mixture-of-Gaussians:
          * Mean shift: Delta_mu = p * amount
          * Variance increase: Delta_sigma^2 = p * (1 - p) * amount^2
          Corridor width expands via sqrt(sigma^2 + Delta_sigma^2).
        """
        prep_events = self.prepare_events(
            events=events,
            detected_slots=detected_slots,
            as_of=as_of,
            horizon=horizon,
            scenario=scenario,
            is_ml=is_ml
        )

        h_len = len(p50_arr)
        new_p50 = p50_arr.copy()
        new_p10 = p10_arr.copy()
        new_p90 = p90_arr.copy()

        # Extract current sigma profile
        sigma_arr = np.maximum(100.0, (new_p90 - new_p50) / k_factor)
        contributions: List[Dict[str, Any]] = []

        for ev in prep_events:
            ev_d = ev["event_date"]
            step_idx = (ev_d - as_of).days - 1
            if not (0 <= step_idx < h_len):
                continue

            amt = ev["amount"]
            prob = ev["probability"]

            if prob >= 1.0:
                new_p50[step_idx:] += amt
                new_p10[step_idx:] += amt
                new_p90[step_idx:] += amt
            elif prob > 0.0:
                delta_mu = prob * amt
                delta_var = prob * (1.0 - prob) * (amt ** 2)

                new_p50[step_idx:] += delta_mu
                sigma_arr[step_idx:] = np.sqrt(sigma_arr[step_idx:] ** 2 + delta_var)
                new_p10[step_idx:] = new_p50[step_idx:] - k_factor * sigma_arr[step_idx:]
                new_p90[step_idx:] = new_p50[step_idx:] + k_factor * sigma_arr[step_idx:]

            if True:  # Include all events in contributions
                contributions.append({
                    "date": ev_d,
                    "category": ev["category_id"],
                    "amount": round(amt, 2),
                    "probability": round(prob, 2),
                    "source": ev["source"],
                    "is_slot_replacement": ev["is_slot_replacement"],
                    "overridden_slot_id": ev["overridden_slot_id"]
                })

        # Monotonicity
        new_p10 = np.minimum(new_p10, new_p50)
        new_p90 = np.maximum(new_p90, new_p50)

        effective_threshold = -float(overdraft_limit)
        prob_neg_arr = np.zeros(h_len, dtype=float)
        for d in range(h_len):
            sig = max(100.0, float(sigma_arr[d]))
            prob_neg_arr[d] = float(norm.cdf((effective_threshold - new_p50[d]) / sig))

        # Recompute p_any analytically from min point
        min_idx = int(np.argmin(new_p50))
        min_val = float(new_p50[min_idx])
        min_sig = max(100.0, float(sigma_arr[min_idx]))
        new_p_any = float(norm.cdf((effective_threshold - min_val) / min_sig))

        return {
            "p10": new_p10,
            "p50": new_p50,
            "p90": new_p90,
            "prob_negative": prob_neg_arr,
            "p_any": max(0.0, min(1.0, new_p_any)),
            "contributions": contributions,
            "processed_events": prep_events
        }
