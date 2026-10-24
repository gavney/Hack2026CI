import math
import time
import numpy as np
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Protocol, Set, Tuple
from backend.core.slots import is_business_day, next_business_day

class Forecaster(Protocol):
    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        seed: int = 0
    ) -> Dict[str, Any]:
        ...

def norm_cdf(x: float) -> float:
    """Cumulative standard normal distribution function (error function based)"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

class ForecasterStubV01:
    """
    Forecasting Engine Stub v0.1 as strictly defined in Section 3.5.2 & 10.2 of TZ:
    - Base trajectory: balance_as_of
    - Known deterministic events: slots, invoices, contracts, taxes, manual inputs
    - Variable flows: 90-day mean daily net flow (excluding transfer_own)
    - Corridor P10..P90: +/- k * std * sqrt(t)
    - Probability of negative balance: Normal CDF around median
    - Output marked with model_version="stub-0.1" and quality="low"
    """
    def __init__(self, k_factor: float = 1.28):
        self.k_factor = k_factor

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        seed: int = 0
    ) -> Dict[str, Any]:
        np.random.seed(seed)
        events = events or []

        # 1. Analyze 90-day variable flows from history
        # Identify discrete categories present in slots/events to prevent double-counting
        discrete_cats = {ev.get('category_id') for ev in events if ev.get('source') in ['slot', 'tax_calendar']}
        exclude_cats = {'cat_transfer_own'} | {c for c in discrete_cats if c}

        if not history.empty and 'operation_date' in history.columns:
            h_df = history.copy()
            h_df['operation_date'] = pd.to_datetime(h_df['operation_date'])
            as_of_dt = pd.to_datetime(as_of)
            h_df = h_df[h_df['operation_date'] <= as_of_dt]
            min_90_date = as_of_dt - pd.Timedelta(days=90)
            window_df = h_df[h_df['operation_date'] >= min_90_date].copy()

            # Exclude own account transfers and discrete slot categories (prevents double-counting)
            window_df = window_df[~window_df['category_id'].isin(exclude_cats)]

            # Daily net flow
            daily = window_df.groupby('operation_date').agg(
                inflow=('amount', lambda x: window_df.loc[x.index][window_df.loc[x.index, 'direction'] == 'Поступление']['amount'].sum()),
                outflow=('amount', lambda x: window_df.loc[x.index][window_df.loc[x.index, 'direction'] == 'Списание']['amount'].sum())
            ).reset_index()
            daily['net'] = daily['inflow'] - daily['outflow']

            if len(daily) > 0:
                mean_daily_net = float(daily['net'].mean())
                mean_daily_inflow = float(daily['inflow'].mean())
                mean_daily_outflow = float(daily['outflow'].mean())
                std_daily_net = float(daily['net'].std())
                if np.isnan(std_daily_net) or std_daily_net < 1000.0:
                    std_daily_net = max(1000.0, abs(mean_daily_net) * 0.5)
            else:
                mean_daily_net = 0.0
                mean_daily_inflow = 0.0
                mean_daily_outflow = 0.0
                std_daily_net = 50000.0
        else:
            mean_daily_net = 0.0
            mean_daily_inflow = 0.0
            mean_daily_outflow = 0.0
            std_daily_net = 50000.0

        # Scenario adjustments
        scenario_type = scenario.get('scenario_type') if scenario else None
        scenario_params = scenario.get('params', {}) if scenario else {}

        adjusted_mean_inflow = mean_daily_inflow
        adjusted_mean_outflow = mean_daily_outflow

        if scenario_type == 'revenue_drop':
            drop_pct = float(scenario_params.get('drop_percent', 20.0)) / 100.0
            adjusted_mean_inflow *= (1.0 - drop_pct)
        elif scenario_type == 'cost_increase':
            increase_pct = float(scenario_params.get('increase_percent', 15.0)) / 100.0
            adjusted_mean_outflow *= (1.0 + increase_pct)

        effective_daily_net = adjusted_mean_inflow - adjusted_mean_outflow

        # 2. Build Event map by day
        # Handle scenario injections and delays
        has_pos_events = any(ev.get('amount', 0) > 0 for ev in events)
        delay_days = int(scenario_params.get('delay_days', 14)) if scenario_type == 'delayed_payment' else 0
        delayed_accum_stub = 0.0

        event_map: Dict[date, List[Dict[str, Any]]] = {}
        for ev in events:
            ev_date = ev['event_date'] if isinstance(ev['event_date'], date) else pd.to_datetime(ev['event_date']).date()
            ev_amt = float(ev['amount'])
            ev_prob = float(ev.get('probability', 1.0))
            ev_cat = ev.get('category_id') or ('cat_revenue_client' if ev_amt > 0 else 'cat_other_out')
            ev_source = ev.get('source', 'manual')

            # Scenario: delayed payment from key client
            if scenario_type == 'delayed_payment' and ev_amt > 0:
                ev_date = ev_date + timedelta(days=delay_days)

            # Scenario: revenue drop reduces expected positive events
            if scenario_type == 'revenue_drop' and ev_amt > 0:
                drop_pct = float(scenario_params.get('drop_percent', 20.0)) / 100.0
                ev_amt = ev_amt * (1.0 - drop_pct)

            # Scenario: cost increase scales regular negative slots/expenses
            if scenario_type == 'cost_increase' and ev_amt < 0:
                inc_pct = float(scenario_params.get('increase_percent', 15.0)) / 100.0
                ev_amt = ev_amt * (1.0 + inc_pct)

            # Weekend shift for mandatory scheduled events
            if not is_business_day(ev_date) and ev_source in ['tax_calendar', 'history', 'slot']:
                ev_date = next_business_day(ev_date)

            effective_amt = ev_amt * ev_prob
            if ev_date not in event_map:
                event_map[ev_date] = []
            event_map[ev_date].append({
                "date": ev_date,
                "category": ev_cat,
                "amount": effective_amt,
                "source": ev_source
            })

        # Scenario: unexpected expense injection
        if scenario_type == 'unexpected_expense':
            exp_date_str = scenario_params.get('expense_date')
            exp_amount = float(scenario_params.get('amount', 250000.0))
            exp_days = int(scenario_params.get('expense_days_ahead', 5))
            if exp_date_str:
                exp_date = pd.to_datetime(exp_date_str).date()
            else:
                exp_date = as_of + timedelta(days=exp_days)
            if exp_date not in event_map:
                event_map[exp_date] = []
            event_map[exp_date].append({
                "date": exp_date,
                "category": "cat_other_out",
                "amount": -abs(exp_amount),
                "source": "scenario"
            })

        # 3. Simulate forward for horizon days
        days_result = []
        contributions = []
        cur_balance = float(balance_as_of)

        first_gap_date = None
        max_gap_prob = 0.0
        total_shortfall_p10 = 0.0

        for t in range(1, horizon + 1):
            day_date = as_of + timedelta(days=t)
            is_workday = is_business_day(day_date)

            # Variable flow addition on business days
            if is_workday:
                flow_in = adjusted_mean_inflow
                if scenario_type == 'delayed_payment' and not has_pos_events:
                    if t <= delay_days:
                        withheld = flow_in * 0.35
                        flow_in -= withheld
                        delayed_accum_stub += withheld
                    elif t == delay_days + 1:
                        flow_in += delayed_accum_stub
                cur_balance += (flow_in - adjusted_mean_outflow)

            # Deterministic events on this date
            day_events = event_map.get(day_date, [])
            for dev in day_events:
                cur_balance += dev['amount']
                contributions.append({
                    "date": dev['date'],
                    "category": dev.get('category') or 'cat_other_out',
                    "amount": round(dev['amount'], 2),
                    "source": dev['source']
                })

            # Corridor standard deviation grows with sqrt(t)
            # Section 3.5.2: k * std * sqrt(t)
            daily_sigma = std_daily_net * math.sqrt(t)
            margin = self.k_factor * daily_sigma

            p50 = cur_balance
            p10 = cur_balance - margin
            p90 = cur_balance + margin

            # Ensure monotonic ordering p10 <= p50 <= p90
            if p10 > p50:
                p10 = p50
            if p90 < p50:
                p90 = p50

            # Probability of negative balance (accounting for overdraft limit)
            # Hard gap threshold = -overdraft_limit
            effective_threshold = -overdraft_limit
            z_score = (effective_threshold - p50) / max(1.0, daily_sigma)
            prob_neg = norm_cdf(z_score)
            prob_neg = max(0.0, min(1.0, prob_neg))

            if prob_neg > max_gap_prob:
                max_gap_prob = prob_neg

            if p10 < effective_threshold:
                shortfall = effective_threshold - p10
                if shortfall > total_shortfall_p10:
                    total_shortfall_p10 = shortfall

            days_result.append({
                "date": day_date,
                "p10": round(p10, 2),
                "p50": round(p50, 2),
                "p90": round(p90, 2),
                "prob_negative": round(prob_neg, 4)
            })

        # Determine the true first cash gap date:
        # Priority 1: Expected hard gap where median p50 < effective_threshold
        # Priority 2: High probability gap where prob_neg >= 0.50
        # Priority 3: Peak stress date where p10 reaches its minimum (if max_gap_prob >= 0.25)
        first_hard_gap_date = None
        first_prob_gap_date = None
        min_p10_date = None
        min_p10_val = float('inf')

        for r in days_result:
            p50_val = r["p50"]
            p10_val = r["p10"]
            prob_neg = r["prob_negative"]
            d_date = r["date"]

            if p10_val < min_p10_val:
                min_p10_val = p10_val
                min_p10_date = d_date

            if p50_val < effective_threshold and first_hard_gap_date is None:
                first_hard_gap_date = d_date

            if prob_neg >= 0.50 and first_prob_gap_date is None:
                first_prob_gap_date = d_date

        if first_hard_gap_date:
            first_gap_date = first_hard_gap_date
        elif first_prob_gap_date:
            first_gap_date = first_prob_gap_date
        elif max_gap_prob >= 0.25:
            first_gap_date = min_p10_date
        else:
            first_gap_date = None

        return {
            "model_version": "stub-0.1",
            "quality": "low",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "contributions": contributions,
            "total_shortfall_p10": round(total_shortfall_p10, 2),
            "first_gap_date": first_gap_date,
            "gap_probability": round(max_gap_prob, 2)
        }


class MonteCarloForecaster:
    """
    Monte Carlo Simulation Forecaster v1.0

    Methodology:
    - Bootstrap resampling of historical daily inflows / outflows
      (weekday-stratified for seasonality)
    - N=1000 independent paths over the forecast horizon
    - Deterministic events (slots, invoices, taxes) injected on exact dates
    - Scenario adjustments (delayed_payment, revenue_drop, cost_increase, unexpected_expense)
    - Empirical percentiles P10 / P50 / P90 from the simulated distribution
    - VaR(95%) and CVaR (Expected Shortfall) from minimum-balance distribution
    - 5 representative sample paths for Debug "spaghetti chart" visualization

    Performance: ~20ms for 1000×90 matrix (fully vectorized NumPy)
    """

    def __init__(self, n_simulations: int = 1000, n_sample_paths: int = 5):
        self.n_simulations = n_simulations
        self.n_sample_paths = n_sample_paths

    def _build_daily_pools(self, history: pd.DataFrame, as_of: date, exclude_cats: Optional[Set[str]] = None):
        """
        Build bootstrap pools of daily (inflow, outflow) grouped by weekday (0=Mon..6=Sun).
        Uses full history (not just 90 days) for richer sampling.
        Excludes cat_transfer_own and any discrete recurring slots (salary, taxes, rent)
        to prevent double-counting with deterministic calendar events.
        Returns:
          weekday_inflows: dict[int, np.array]
          weekday_outflows: dict[int, np.array]
          all_inflows: np.array   (fallback)
          all_outflows: np.array  (fallback)
        """
        if history.empty or 'operation_date' not in history.columns:
            # Fallback: zero-knowledge uniform noise
            fallback = np.array([0.0])
            return {w: fallback for w in range(7)}, {w: fallback for w in range(7)}, fallback, fallback

        h_df = history.copy()
        h_df['operation_date'] = pd.to_datetime(h_df['operation_date'])
        as_of_dt = pd.to_datetime(as_of)
        h_df = h_df[h_df['operation_date'] <= as_of_dt]

        # Exclude own transfers and discrete recurring slot categories (double-counting prevention)
        filter_cats = {'cat_transfer_own'}
        if exclude_cats:
            filter_cats.update(exclude_cats)
        h_df = h_df[~h_df['category_id'].isin(filter_cats)]

        if h_df.empty:
            fallback = np.array([0.0])
            return {w: fallback for w in range(7)}, {w: fallback for w in range(7)}, fallback, fallback

        # Daily aggregation
        daily_in = h_df[h_df['direction'] == 'Поступление'].groupby('operation_date')['amount'].sum()
        daily_out = h_df[h_df['direction'] == 'Списание'].groupby('operation_date')['amount'].sum()

        # Build full daily index
        all_dates = pd.date_range(h_df['operation_date'].min(), as_of_dt, freq='D')
        daily_df = pd.DataFrame({'operation_date': all_dates})
        daily_df['inflow'] = daily_df['operation_date'].map(daily_in).fillna(0.0).values
        daily_df['outflow'] = daily_df['operation_date'].map(daily_out).fillna(0.0).values
        daily_df['weekday'] = daily_df['operation_date'].dt.day_of_week

        all_inflows = daily_df['inflow'].values.astype(np.float64)
        all_outflows = daily_df['outflow'].values.astype(np.float64)

        weekday_inflows = {}
        weekday_outflows = {}
        for w in range(7):
            mask = daily_df['weekday'] == w
            wk_in = daily_df.loc[mask, 'inflow'].values.astype(np.float64)
            wk_out = daily_df.loc[mask, 'outflow'].values.astype(np.float64)
            weekday_inflows[w] = wk_in if len(wk_in) > 0 else all_inflows
            weekday_outflows[w] = wk_out if len(wk_out) > 0 else all_outflows

        return weekday_inflows, weekday_outflows, all_inflows, all_outflows

    def _build_event_map(self, events: List[Dict], scenario_type: Optional[str],
                         scenario_params: Dict, as_of: date) -> Dict[date, float]:
        """
        Build deterministic event map: date -> total signed amount.
        Handles scenario delays and unexpected expenses.
        Returns contributions list for the response as well.
        """
        event_map: Dict[date, float] = {}
        contributions: List[Dict[str, Any]] = []

        for ev in events:
            ev_date = ev['event_date'] if isinstance(ev['event_date'], date) else pd.to_datetime(ev['event_date']).date()
            ev_amt = float(ev['amount'])
            ev_prob = float(ev.get('probability', 1.0))
            ev_cat = ev.get('category_id') or ('cat_revenue_client' if ev_amt > 0 else 'cat_other_out')
            ev_source = ev.get('source', 'manual')

            # Scenario: delayed payment from key client
            if scenario_type == 'delayed_payment' and ev_amt > 0:
                delay_days = int(scenario_params.get('delay_days', 14))
                ev_date = ev_date + timedelta(days=delay_days)

            # Scenario: revenue drop reduces expected positive events
            if scenario_type == 'revenue_drop' and ev_amt > 0:
                drop_pct = float(scenario_params.get('drop_percent', 20.0)) / 100.0
                ev_amt = ev_amt * (1.0 - drop_pct)

            # Scenario: cost increase scales regular negative slots/expenses
            if scenario_type == 'cost_increase' and ev_amt < 0:
                inc_pct = float(scenario_params.get('increase_percent', 15.0)) / 100.0
                ev_amt = ev_amt * (1.0 + inc_pct)

            # Weekend shift for mandatory scheduled events
            if not is_business_day(ev_date) and ev_source in ['tax_calendar', 'history', 'slot']:
                ev_date = next_business_day(ev_date)

            effective_amt = ev_amt * ev_prob
            event_map[ev_date] = event_map.get(ev_date, 0.0) + effective_amt
            contributions.append({
                "date": ev_date,
                "category": ev_cat,
                "amount": round(effective_amt, 2),
                "source": ev_source
            })

        # Scenario: unexpected expense injection
        if scenario_type == 'unexpected_expense':
            exp_date_str = scenario_params.get('expense_date')
            exp_amount = float(scenario_params.get('amount', 250000.0))
            exp_days = int(scenario_params.get('expense_days_ahead', 5))
            if exp_date_str:
                exp_date = pd.to_datetime(exp_date_str).date()
            else:
                exp_date = as_of + timedelta(days=exp_days)
            event_map[exp_date] = event_map.get(exp_date, 0.0) - abs(exp_amount)
            contributions.append({
                "date": exp_date,
                "category": "cat_other_out",
                "amount": -abs(exp_amount),
                "source": "scenario"
            })

        return event_map, contributions

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        seed: int = 42
    ) -> Dict[str, Any]:
        t_start = time.perf_counter()
        rng = np.random.default_rng(seed)
        events = events or []
        N = self.n_simulations
        H = horizon

        # --- Scenario parsing ---
        scenario_type = scenario.get('scenario_type') if scenario else None
        scenario_params = scenario.get('params', {}) if scenario else {}

        # --- Double-counting prevention: isolate recurring slot categories ---
        discrete_cats = {ev.get('category_id') for ev in events if ev.get('source') in ['slot', 'tax_calendar']}
        exclude_cats = {c for c in discrete_cats if c}

        # --- Build bootstrap pools ---
        wk_in, wk_out, all_in, all_out = self._build_daily_pools(history, as_of, exclude_cats=exclude_cats)

        # --- Scenario multipliers for inflow / outflow ---
        inflow_mult = 1.0
        outflow_mult = 1.0
        if scenario_type == 'revenue_drop':
            drop_pct = float(scenario_params.get('drop_percent', 20.0)) / 100.0
            inflow_mult = 1.0 - drop_pct
        elif scenario_type == 'cost_increase':
            increase_pct = float(scenario_params.get('increase_percent', 15.0)) / 100.0
            outflow_mult = 1.0 + increase_pct

        # --- Deterministic event map ---
        event_map, contributions = self._build_event_map(events, scenario_type, scenario_params, as_of)

        # --- Delayed payment tracking for statistical flows (if no discrete events) ---
        has_pos_events = any(ev.get('amount', 0) > 0 for ev in events)
        delay_days = int(scenario_params.get('delay_days', 14)) if scenario_type == 'delayed_payment' else 0
        delayed_accumulated = np.zeros(N, dtype=np.float64)

        # --- Simulate N paths × H days ---
        paths = np.zeros((N, H), dtype=np.float64)
        cur = np.full(N, float(balance_as_of), dtype=np.float64)

        dates_list = []
        for d in range(H):
            day_date = as_of + timedelta(days=d + 1)
            dates_list.append(day_date)
            w = day_date.weekday()

            # Bootstrap sampling (weekday-stratified)
            inf_pool = wk_in[w]
            outf_pool = wk_out[w]

            sampled_in = inf_pool[rng.integers(0, len(inf_pool), size=N)] * inflow_mult
            sampled_out = outf_pool[rng.integers(0, len(outf_pool), size=N)] * outflow_mult

            # Delayed payment model when no discrete future events exist
            if scenario_type == 'delayed_payment' and not has_pos_events:
                if d < delay_days:
                    withheld = sampled_in * 0.35
                    sampled_in = sampled_in - withheld
                    delayed_accumulated += withheld
                elif d == delay_days:
                    sampled_in = sampled_in + delayed_accumulated

            net_flows = sampled_in - sampled_out
            cur = cur + net_flows

            # Add deterministic events on this day (same for all paths)
            ev_amount = event_map.get(day_date, 0.0)
            if ev_amount != 0.0:
                cur = cur + ev_amount

            paths[:, d] = cur

        # --- Compute empirical percentiles ---
        p10_arr = np.percentile(paths, 10, axis=0)
        p50_arr = np.percentile(paths, 50, axis=0)
        p90_arr = np.percentile(paths, 90, axis=0)

        # --- Probability of cash gap per day ---
        effective_threshold = -overdraft_limit
        prob_neg_arr = np.mean(paths < effective_threshold, axis=0)

        # --- Build days result ---
        days_result = []
        first_gap_date = None
        max_gap_prob = 0.0
        total_shortfall_p10 = 0.0

        first_hard_gap_date = None
        first_prob_gap_date = None
        min_p10_date = None
        min_p10_val = float('inf')

        for d in range(H):
            day_date = dates_list[d]
            p10_val = float(p10_arr[d])
            p50_val = float(p50_arr[d])
            p90_val = float(p90_arr[d])
            prob_neg = float(prob_neg_arr[d])

            if p10_val < min_p10_val:
                min_p10_val = p10_val
                min_p10_date = day_date

            if p50_val < effective_threshold and first_hard_gap_date is None:
                first_hard_gap_date = day_date

            if prob_neg >= 0.50 and first_prob_gap_date is None:
                first_prob_gap_date = day_date

            if prob_neg > max_gap_prob:
                max_gap_prob = prob_neg

            if p10_val < effective_threshold:
                shortfall = effective_threshold - p10_val
                if shortfall > total_shortfall_p10:
                    total_shortfall_p10 = shortfall

            days_result.append({
                "date": day_date,
                "p10": round(p10_val, 2),
                "p50": round(p50_val, 2),
                "p90": round(p90_val, 2),
                "prob_negative": round(prob_neg, 4)
            })

        if first_hard_gap_date:
            first_gap_date = first_hard_gap_date
        elif first_prob_gap_date:
            first_gap_date = first_prob_gap_date
        elif max_gap_prob >= 0.25:
            first_gap_date = min_p10_date
        else:
            first_gap_date = None

        # --- VaR(95%) and CVaR (Expected Shortfall) ---
        # VaR = maximum potential loss at 95% confidence = worst 5th percentile of minimum balances
        min_balances = np.min(paths, axis=1)
        var_5th_pctile = np.percentile(min_balances, 5)
        var_95 = max(0.0, float(-var_5th_pctile)) if var_5th_pctile < 0 else 0.0

        # CVaR = expected value of losses beyond VaR
        worst_mask = min_balances <= var_5th_pctile
        if np.any(worst_mask):
            cvar_95 = max(0.0, float(-np.mean(min_balances[worst_mask])))
        else:
            cvar_95 = var_95

        # --- Select representative sample paths ---
        # Pick 5 paths at P5, P25, P50, P75, P95 of terminal balance
        sorted_idx = np.argsort(paths[:, -1])
        pctile_positions = [0.05, 0.25, 0.50, 0.75, 0.95]
        sample_indices = [int(sorted_idx[min(int(p * N), N - 1)]) for p in pctile_positions]
        sample_paths = [
            [round(float(paths[idx, d]), 2) for d in range(H)]
            for idx in sample_indices
        ]

        t_elapsed = time.perf_counter() - t_start

        # --- Simulation metadata ---
        simulation_meta = {
            "engine": "monte-carlo",
            "iterations": N,
            "horizon_days": H,
            "execution_time_ms": round(t_elapsed * 1000, 2),
            "var_95": round(var_95, 2),
            "cvar_95": round(cvar_95, 2),
            "prob_gap_max": round(max_gap_prob, 4),
            "inflow_multiplier": inflow_mult,
            "outflow_multiplier": outflow_mult,
            "seed": seed,
            "sample_path_labels": ["P5 (pessimistic)", "P25", "P50 (median)", "P75", "P95 (optimistic)"]
        }

        return {
            "model_version": "monte-carlo-v1.0",
            "quality": "medium",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "contributions": contributions,
            "total_shortfall_p10": round(total_shortfall_p10, 2),
            "first_gap_date": first_gap_date,
            "gap_probability": round(max_gap_prob, 4),
            "sample_paths": sample_paths,
            "simulation_meta": simulation_meta
        }
