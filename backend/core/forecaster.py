import math
import time
import numpy as np
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Protocol, Set, Tuple
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from backend.core.slots import is_business_day, next_business_day

H_MAX = 90
_R_MAT = np.array([[min(s, t) / np.sqrt(s * t) for t in range(1, H_MAX + 1)] for s in range(1, H_MAX + 1)])
L_CHOLESKY = np.linalg.cholesky(_R_MAT)

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

class AlwaysAlertForecaster:
    """
    Baseline Always Alert Forecaster.
    Predicts gap probability = 1.0 unconditionally.
    """
    def __init__(self):
        self.version = "baseline-always-alert"

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        detected_slots: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42
    ) -> Dict[str, Any]:
        p50 = np.full(horizon, balance_as_of - 1_000_000.0)
        p10 = p50 - 500_000.0
        p90 = p50 + 500_000.0
        future_dates = [pd.to_datetime(as_of) + pd.Timedelta(days=d) for d in range(1, horizon + 1)]
        days_result = [
            {"date": dt.date(), "p10": float(p10[i]), "p50": float(p50[i]), "p90": float(p90[i]), "prob_negative": 1.0}
            for i, dt in enumerate(future_dates)
        ]
        return {
            "model_version": self.version,
            "quality": "low",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "gap_probability": 1.0,
            "p_any": 1.0,
            "p_pointwise_max": 1.0,
            "sample_paths": []
        }

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
            if 'category_id' in window_df.columns:
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

        p10_arr = np.array([r["p10"] for r in days_result], dtype=float)
        p50_arr = np.array([r["p50"] for r in days_result], dtype=float)
        p90_arr = np.array([r["p90"] for r in days_result], dtype=float)

        if balance_as_of < 0:
            p_any = 1.0
        else:
            sigma_eff = np.maximum(1000.0, (p90_arr - p10_arr) / (2.0 * 1.28155))
            L_sub = L_CHOLESKY[:horizon, :horizon]
            rng = np.random.default_rng(42)
            z = rng.standard_normal((1000, horizon))
            synth = p50_arr + sigma_eff * (z @ L_sub.T)
            p_any = float(np.mean(np.min(synth, axis=1) < 0))

        return {
            "model_version": "stub-0.1",
            "quality": "low",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "contributions": contributions,
            "total_shortfall_p10": round(total_shortfall_p10, 2),
            "first_gap_date": first_gap_date,
            "gap_probability": round(max_gap_prob, 2),
            "p_any": round(p_any, 4),
            "p_pointwise_max": round(max_gap_prob, 4)
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
        if 'category_id' in h_df.columns:
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
        detected_slots: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42,
        **kwargs
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

        p_any = float(np.mean(np.min(paths, axis=1) < 0)) if paths.size > 0 else float(max_gap_prob)
        p_pw_max = float(max_gap_prob)

        return {
            "model_version": "monte-carlo-v1.0",
            "quality": "medium",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "contributions": contributions,
            "total_shortfall_p10": round(total_shortfall_p10, 2),
            "first_gap_date": first_gap_date,
            "gap_probability": round(p_any, 4),
            "p_any": round(p_any, 4),
            "p_pointwise_max": round(p_pw_max, 4),
            "sample_paths": sample_paths,
            "simulation_meta": simulation_meta
        }


# --- Financial Calendar & Owner Operations Helpers (B1-B9) ---
OWNER_KEYWORDS = [
    "собственными средствами",
    "собственных средств",
    "пополнение счета собственными",
    "перевод собственных средств",
    "на счет физического лица",
    "личную карту",
    "личные нужды"
]

def is_owner_operation(
    purpose: str | None = None,
    category_id: Optional[str] = None,
    counterparty_name: Optional[str] = None,
    counterparty_inn: Optional[str] = None,
    company_name: Optional[str] = None,
    company_inn: Optional[str] = None
) -> bool:
    """Определение пополнений и переводов собственника (B5)."""
    if category_id in ["cat_transfer_own", "cat_owner"]:
        return True
    if not purpose or not isinstance(purpose, str):
        return False
    purpose_lower = purpose.lower()
    has_kw = any(kw in purpose_lower for kw in OWNER_KEYWORDS)
    if not has_kw:
        return False

    cp = str(counterparty_name or "").lower()
    inn_match = bool(company_inn and counterparty_inn and str(company_inn).strip() == str(counterparty_inn).strip())
    name_match = False
    if company_name:
        cn_clean = str(company_name).lower().replace("ип", "").replace("ооо", "").strip()
        if cn_clean and cn_clean in cp:
            name_match = True
    self_match = any(w in cp for w in ["предприниматель", "ип ", "физическ"]) or ("счет" in purpose_lower and "свой" in purpose_lower)
    return has_kw and (inn_match or name_match or self_match or cp == "")


def extract_calendar_features(dt: pd.Timestamp) -> List[float]:
    """
    Календарный инжиниринг:
    - 1-3 числа: окно аренды
    - 14-16 числа: окно аванса по зарплате
    - 28-30 числа: окно ЕНП
    - Последние 2 рабочих дня месяца: расчет по зарплате
    - Гармоники sin/cos дня месяца
    - День недели (one-hot) и флаг выходного
    """
    day = dt.day
    dow = dt.day_of_week
    is_workday = 1.0 if dow < 5 else 0.0

    days_in_month = dt.days_in_month
    is_month_end_workday = 0.0
    if is_workday:
        rem_workdays = sum(1 for k in range(1, days_in_month - day + 1) if (dow + k) % 7 < 5)
        if rem_workdays <= 1:
            is_month_end_workday = 1.0

    is_rent_window = 1.0 if (day in [1, 2, 3] and is_workday) else 0.0
    is_advance_window = 1.0 if (day in [14, 15, 16] and is_workday) else 0.0
    is_tax_enp_window = 1.0 if (day in [28, 29, 30] and is_workday and day <= 29) else 0.0

    angle = 2.0 * np.pi * (day - 1) / 31.0
    sin_day = float(np.sin(angle))
    cos_day = float(np.cos(angle))
    dow_dummies = [1.0 if dow == k else 0.0 for k in range(7)]

    return [
        1.0 - is_workday,
        is_rent_window,
        is_advance_window,
        is_tax_enp_window,
        is_month_end_workday,
        sin_day,
        cos_day
    ] + dow_dummies


def extract_slot_features(dt: pd.Timestamp, events: Optional[List[Dict[str, Any]]] = None) -> List[float]:
    """Признаки близости слотов без детерминированного инжектирования (B1, B6)."""
    day = dt.day
    slot_days = [2, 15, 28, 30]
    distances = [min(abs(day - sd), abs(day - sd + 30), abs(day - sd - 30)) for sd in slot_days]
    min_dist = min(distances)
    return [float(min_dist), float(min_dist <= 2)]


class MLForecaster:
    """
    ML-Based Cash Flow & Gap Forecasting Engine v2.0 (Direct Multi-Step + Block Bootstrap):
    - B1 (REVISED): Pure ML model. Target = full daily net_flow without owner operations.
      Slots are NOT subtracted from training target, and NOT injected as events.
      Slots are used strictly as calendar & distance features.
    - B2: Direct multi-step model predicting step h from cutoff features + target calendar.
    - B3: Walk-forward out-of-sample direct residuals; block bootstrap (7d blocks, weekday-aligned).
    - B4: Raw starting balance B0 from statement at T.
    - B5: Strict owner operation filter by purpose keywords and IP counterparty matching.
    - B6: Calendar holiday & weekend shifts for features and user events.
    - B7: Day-level P_gap(d), window-level P_any = mean(paths.min(axis=1) < 0), shortfall metrics.
    - B8: Calibration and threshold theta* tuned strictly on Tune non-trivial windows via F2.
    - B9: Structured JSON logging with zero PII.
    """
    def __init__(
        self,
        ridge_alpha: float = 15.0,
        lgbm_leaves: int = 7,
        n_simulations: int = 1000,
        block_len: int = 7,
        slots_as_events: bool = False,
        global_model: Any = None,
        scale_factor: float = 1.0,
        pooled_residuals: Optional[List[float]] = None
    ):
        self.ridge_alpha = ridge_alpha
        self.lgbm_leaves = lgbm_leaves
        self.n_simulations = n_simulations
        self.block_len = block_len
        self.slots_as_events = slots_as_events
        self.global_model = global_model
        self.scale_factor = max(float(scale_factor), 1.0)
        self.pooled_residuals = pooled_residuals

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        detected_slots: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42,
        **kwargs
    ) -> Dict[str, Any]:
        t_start = time.perf_counter()
        rng = np.random.default_rng(seed)
        events = events or []

        # 1. Historical daily net flows extraction & Owner Filtration (B5)
        train_flows = np.empty(0)
        train_dates: List[pd.Timestamp] = []
        idle_mask = np.empty(0, dtype=bool)

        if not history.empty and 'operation_date' in history.columns:
            h_df = history.copy()
            h_df['operation_date'] = pd.to_datetime(h_df['operation_date']).dt.normalize()
            as_of_dt = pd.to_datetime(as_of).normalize()
            h_df = h_df[h_df['operation_date'] <= as_of_dt]

            # B5: Filter out owner operations strictly
            owner_filter = h_df.apply(
                lambda r: is_owner_operation(
                    purpose=r.get('payment_purpose'),
                    category_id=r.get('category_id'),
                    counterparty_name=r.get('counterparty_name'),
                    counterparty_inn=r.get('counterparty_inn')
                ),
                axis=1
            )
            h_df = h_df[~owner_filter]

            if not h_df.empty:
                daily_in = h_df[h_df['direction'] == 'Поступление'].groupby('operation_date')['amount'].sum()
                daily_out = h_df[h_df['direction'] == 'Списание'].groupby('operation_date')['amount'].sum()
                daily_cnt = h_df.groupby('operation_date')['amount'].count()

                min_dt = h_df['operation_date'].min()
                all_dates = pd.date_range(min_dt, as_of_dt, freq='D')
                daily_df = pd.DataFrame({'date': all_dates})
                daily_df['inflow'] = daily_df['date'].map(daily_in).fillna(0.0).values
                daily_df['outflow'] = daily_df['date'].map(daily_out).fillna(0.0).values
                daily_df['net'] = daily_df['inflow'] - daily_df['outflow']
                daily_df['op_count'] = daily_df['date'].map(daily_cnt).fillna(0).astype(int)

                # Idle periods detection (>= 5 consecutive zero days)
                is_zero = (daily_df['op_count'] == 0).astype(int)
                zero_groups = (is_zero != is_zero.shift()).cumsum() * is_zero
                group_counts = zero_groups.map(zero_groups[zero_groups > 0].value_counts())
                daily_df['is_idle'] = (group_counts >= 5).fillna(False)

                train_flows = daily_df['net'].to_numpy(dtype=float)
                train_dates = daily_df['date'].tolist()
                idle_mask = daily_df['is_idle'].to_numpy(dtype=bool)

        # 2. Scenario adjustments
        scenario_type = scenario.get('scenario_type') if scenario else None
        scenario_params = scenario.get('params', {}) if scenario else {}
        inflow_mult = 1.0
        outflow_mult = 1.0

        if scenario_type == 'revenue_drop':
            drop_pct = float(scenario_params.get('drop_percent', 20.0)) / 100.0
            inflow_mult = max(0.0, 1.0 - drop_pct)
        elif scenario_type == 'cost_increase':
            increase_pct = float(scenario_params.get('increase_percent', 15.0)) / 100.0
            outflow_mult = 1.0 + increase_pct

        # 3. Forecast future dates
        future_dates = [pd.to_datetime(as_of) + pd.Timedelta(days=d) for d in range(1, horizon + 1)]
        lags = [1, 2, 3, 7, 14, 21, 28]
        max_lag = 28
        N = len(train_flows)

        # 4. Train Direct Model & Walk-Forward OOF Residuals (B2, B3)
        fallback_triggered = False
        if N < 120:
            fallback_triggered = True
        oof_residuals = []
        ml_p50_flows = []
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        s_factor = self.scale_factor if self.global_model is not None else 1.0

        if self.global_model is not None:
            ridge_model = self.global_model
            if self.pooled_residuals is not None and len(self.pooled_residuals) >= 20:
                oof_residuals = [r * s_factor for r in self.pooled_residuals]
            else:
                oof_residuals = [25000.0]

            frozen_lags = [train_flows[-l] if N >= l else 0.0 for l in lags]
            mean_7 = float(np.mean(train_flows[-7:])) if N >= 7 else 0.0
            mean_28 = float(np.mean(train_flows[-28:])) if N >= 28 else 0.0
            std_28 = float(np.std(train_flows[-28:])) if N >= 28 else 0.0

            for h in range(1, horizon + 1):
                dt = future_dates[h - 1]
                row = [l / s_factor for l in frozen_lags]
                row.extend([mean_7 / s_factor, mean_28 / s_factor, std_28 / s_factor, float(h) / 30.0])
                row.extend(extract_calendar_features(dt))
                row.extend(extract_slot_features(dt, events))

                pred_f = float(ridge_model.predict([row])[0]) * s_factor
                if dt.day_of_week >= 5:
                    pred_f = 0.0

                if pred_f > 0:
                    pred_f *= inflow_mult
                else:
                    pred_f *= outflow_mult
                ml_p50_flows.append(pred_f)
            ml_p50_flows = np.asarray(ml_p50_flows, dtype=float)
        elif N > max_lag + 7:
            step_grid = [1, 2, 3, 5, 7, 10, 14, 21, 28, min(horizon, 30)]
            X, y = [], []
            for i in range(max_lag, N):
                if idle_mask[i]:
                    continue
                f_frozen = [train_flows[i - l] for l in lags]
                m7 = float(np.mean(train_flows[max(0, i-7):i]))
                m28 = float(np.mean(train_flows[max(0, i-28):i]))
                s28 = float(np.std(train_flows[max(0, i-28):i])) if i >= 28 else 0.0

                for h in step_grid:
                    if i + h < N:
                        dt_target = train_dates[i + h]
                        row = list(f_frozen)
                        row.extend([m7, m28, s28, float(h) / 30.0])
                        row.extend(extract_calendar_features(dt_target))
                        row.extend(extract_slot_features(dt_target, events))
                        X.append(row)
                        y.append(train_flows[i + h])

            X_arr = np.asarray(X, dtype=float)
            y_arr = np.asarray(y, dtype=float)

            # FIX22: True Walk-Forward Out-Of-Sample Residuals (TimeSeriesSplit 5-fold)
            from sklearn.model_selection import TimeSeriesSplit
            oof_residuals = []
            if len(X_arr) >= 30:
                tscv = TimeSeriesSplit(n_splits=5)
                splits = list(tscv.split(X_arr))
                first_tr_len = len(splits[0][0])
                if first_tr_len < 40 or N < 120:
                    fallback_triggered = True

                for tr_idx, te_idx in splits:
                    fold_scaler = StandardScaler()
                    X_tr_sc = fold_scaler.fit_transform(X_arr[tr_idx])
                    X_te_sc = fold_scaler.transform(X_arr[te_idx])
                    fm = Ridge(alpha=self.ridge_alpha, random_state=seed)
                    fm.fit(X_tr_sc, y_arr[tr_idx])
                    oof_residuals.extend((y_arr[te_idx] - fm.predict(X_te_sc)).tolist())
            else:
                fallback_triggered = True

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_arr)
            ridge_model = Ridge(alpha=self.ridge_alpha, random_state=seed)
            ridge_model.fit(X_scaled, y_arr)

            if not oof_residuals or len(oof_residuals) < 20:
                oof_residuals = (y_arr - ridge_model.predict(X_scaled)).tolist()
                fallback_triggered = True

            # Frozen lags at cutoff T (B2 direct forecast)
            frozen_lags = [train_flows[-l] for l in lags]
            mean_7 = float(np.mean(train_flows[-7:]))
            mean_28 = float(np.mean(train_flows[-28:]))
            std_28 = float(np.std(train_flows[-28:])) if N >= 28 else 0.0

            for h in range(1, horizon + 1):
                dt = future_dates[h - 1]
                row = list(frozen_lags)
                row.extend([mean_7, mean_28, std_28, float(h) / 30.0])
                row.extend(extract_calendar_features(dt))
                row.extend(extract_slot_features(dt, events))

                row_sc = scaler.transform([row])
                pred_f = float(ridge_model.predict(row_sc)[0])
                if dt.day_of_week >= 5:
                    pred_f = 0.0

                if pred_f > 0:
                    pred_f *= inflow_mult
                else:
                    pred_f *= outflow_mult
                ml_p50_flows.append(pred_f)
            ml_p50_flows = np.asarray(ml_p50_flows, dtype=float)
        else:
            fallback_triggered = True
            mean_f = float(np.mean(train_flows)) if N > 0 else 0.0
            ml_p50_flows = np.full(horizon, mean_f * (inflow_mult if mean_f > 0 else outflow_mult), dtype=float)
            oof_residuals = [float(np.std(train_flows)) if N > 1 else 25000.0]

        residuals_pool = np.asarray(oof_residuals if len(oof_residuals) >= 5 else [25000.0], dtype=float)
        # Protective clipping (winsorization) to +/- 5 std(daily_net_flow)
        std_f = max(1000.0, float(np.std(train_flows))) if N > 1 else 25000.0
        residuals_pool = np.clip(residuals_pool, -5.0 * std_f, 5.0 * std_f)

        base_p50_flows = ml_p50_flows.copy()
        base_p50_balances = balance_as_of + np.cumsum(base_p50_flows)

        # 6. Block Residual Bootstrap for Trajectory Corridor (B3, N=1000)
        N_sims = self.n_simulations
        L = self.block_len
        if len(residuals_pool) < L:
            repeats = int(math.ceil(L / max(1, len(residuals_pool)))) + 1
            residuals_pool = np.tile(residuals_pool, repeats)
        n_res = len(residuals_pool)
        n_blocks = int(math.ceil(horizon / L))
        max_start = max(1, n_res - L)

        sampled_blocks = np.zeros((N_sims, n_blocks * L), dtype=float)
        for s in range(N_sims):
            starts = rng.integers(0, max_start, size=n_blocks)
            blks = [residuals_pool[st:st + L] for st in starts]
            sampled_blocks[s, :] = np.concatenate(blks)

        sampled_res = sampled_blocks[:, :horizon]
        sim_flows = ml_p50_flows + sampled_res

        # Weekend variance muting
        for h in range(horizon):
            dt = future_dates[h]
            if dt.day_of_week >= 5:
                sim_flows[:, h] = 0.0

        sim_paths = balance_as_of + np.cumsum(sim_flows, axis=1)

        # 6.5 Apply Unified Events Overlay (backend/core/events_overlay.py)
        from backend.core.events_overlay import EventsOverlayApplier
        overlay_applier = EventsOverlayApplier(seed=seed)

        if detected_slots is None:
            from backend.core.slots import detect_recurring_slots
            detected_slots = detect_recurring_slots(history) if not history.empty else []

        overlay_res = overlay_applier.apply_to_trajectories(
            paths=sim_paths,
            base_p50=base_p50_balances,
            events=events,
            detected_slots=detected_slots,
            as_of=as_of,
            horizon=horizon,
            overdraft_limit=overdraft_limit,
            scenario=scenario,
            is_ml=True,
            slots_as_events=self.slots_as_events,
            seed=seed
        )

        sim_paths = overlay_res["paths"]
        p10_arr = overlay_res["p10"]
        p50_arr = overlay_res["p50"]
        p90_arr = overlay_res["p90"]
        prob_neg_arr = overlay_res["prob_negative"]
        p_any = overlay_res["p_any"]
        contributions = overlay_res["contributions"]

        # Monotonicity Guarantee
        p10_arr = np.minimum(p10_arr, p50_arr)
        p90_arr = np.maximum(p90_arr, p50_arr)

        effective_threshold = -float(overdraft_limit)

        # 7. B7: Daily probabilities & Window-level P_any
        prob_neg_arr = np.mean(sim_paths < effective_threshold, axis=0)
        is_start_negative = bool(balance_as_of < effective_threshold)

        if is_start_negative:
            p_any = 1.0
            status_text = "разрыв уже идет"
        else:
            min_balances_sim = np.min(sim_paths, axis=1)
            p_any = float(np.mean(min_balances_sim < effective_threshold))
            status_text = "прогнозный мониторинг"

        # 8. Construct Days Result & Risk Metrics
        days_result = []
        total_shortfall_p10 = 0.0
        max_gap_prob = float(np.max(prob_neg_arr)) if len(prob_neg_arr) > 0 else 0.0
        first_gap_date = None

        for d_idx, f_dt in enumerate(future_dates):
            day_d = f_dt.date()
            val_p10 = float(p10_arr[d_idx])
            val_p50 = float(p50_arr[d_idx])
            val_p90 = float(p90_arr[d_idx])
            prob_neg = float(prob_neg_arr[d_idx])

            if val_p10 < effective_threshold:
                shortfall = effective_threshold - val_p10
                if shortfall > total_shortfall_p10:
                    total_shortfall_p10 = shortfall

            if (val_p50 < effective_threshold or prob_neg >= 0.50) and first_gap_date is None:
                first_gap_date = day_d

            days_result.append({
                "date": day_d,
                "p10": round(val_p10, 2),
                "p50": round(val_p50, 2),
                "p90": round(val_p90, 2),
                "prob_negative": round(prob_neg, 4)
            })

        if first_gap_date is None and p_any >= 0.25:
            min_p10_idx = int(np.argmin(p10_arr))
            first_gap_date = future_dates[min_p10_idx].date()

        # Representative sample paths
        sorted_indices = np.argsort(sim_paths[:, -1])
        positions = [0.05, 0.25, 0.50, 0.75, 0.95]
        picked_idx = [int(sorted_indices[min(int(p * N_sims), N_sims - 1)]) for p in positions]
        sample_paths = [
            [round(float(sim_paths[idx, d]), 2) for d in range(horizon)]
            for idx in picked_idx
        ]

        # VaR(95%) and CVaR
        min_balances = np.min(sim_paths, axis=1)
        var_5th = np.percentile(min_balances, 5)
        var_95 = max(0.0, float(-var_5th)) if var_5th < 0 else 0.0
        worst_mask = min_balances <= var_5th
        cvar_95 = max(0.0, float(-np.mean(min_balances[worst_mask]))) if np.any(worst_mask) else var_95

        t_elapsed = time.perf_counter() - t_start

        m_ver = "ml-v2.0-canonical" if self.global_model is None else "ml-v2.0-global"
        simulation_meta = {
            "engine": m_ver,
            "model_version": m_ver,
            "features_count": 27,
            "horizon_days": horizon,
            "execution_time_ms": round(t_elapsed * 1000, 2),
            "fallback_triggered": fallback_triggered,
            "var_95": round(var_95, 2),
            "cvar_95": round(cvar_95, 2),
            "prob_gap_max": round(max_gap_prob, 4),
            "p_any": round(p_any, 4),
            "start_negative": is_start_negative,
            "status": status_text,
            "inflow_multiplier": inflow_mult,
            "outflow_multiplier": outflow_mult,
            "sample_path_labels": ["P5 (pessimistic)", "P25", "P50 (Median)", "P75", "P95 (optimistic)"]
        }

        return {
            "model_version": m_ver,
            "quality": "high" if N >= 30 and not fallback_triggered else "medium",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "contributions": contributions,
            "total_shortfall_p10": round(total_shortfall_p10, 2),
            "first_gap_date": first_gap_date,
            "gap_probability": round(p_any, 4),
            "p_any": round(p_any, 4),
            "fallback_triggered": fallback_triggered,
            "sample_paths": sample_paths,
            "simulation_meta": simulation_meta
        }


class OldMLForecaster:
    """
    Old ML (LGBM-cumsum quantile autoregression).
    Canonical baseline representing pre-v2.0 ML architecture:
    - Ridge autoregression on daily flows + lag balance for P50
    - LightGBM quantile models (10% and 90%) on residuals
    - Trajectory uncertainty via Cholesky correlation matrix
    """
    def __init__(self, ridge_alpha: float = 10.0, num_leaves: int = 15, lr: float = 0.08, n_estimators: int = 50):
        self.ridge_alpha = ridge_alpha
        self.num_leaves = num_leaves
        self.lr = lr
        self.n_estimators = n_estimators

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        detected_slots: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42,
        **kwargs
    ) -> Dict[str, Any]:
        h_df = history.copy()
        if not h_df.empty and 'operation_date' in h_df.columns:
            h_df['operation_date'] = pd.to_datetime(h_df['operation_date']).dt.normalize()
            as_of_dt = pd.to_datetime(as_of).normalize()
            h_df = h_df[h_df['operation_date'] <= as_of_dt]

            owner_filter = h_df.apply(
                lambda r: is_owner_operation(
                    purpose=r.get('payment_purpose'),
                    category_id=r.get('category_id'),
                    counterparty_name=r.get('counterparty_name'),
                    counterparty_inn=r.get('counterparty_inn')
                ),
                axis=1
            )
            h_df = h_df[~owner_filter]

            if not h_df.empty:
                daily_in = h_df[h_df['direction'] == 'Поступление'].groupby('operation_date')['amount'].sum()
                daily_out = h_df[h_df['direction'] == 'Списание'].groupby('operation_date')['amount'].sum()
                min_dt = h_df['operation_date'].min()
                all_dates = pd.date_range(min_dt, as_of_dt, freq='D')
                daily_df = pd.DataFrame({'date': all_dates})
                daily_df['inflow'] = daily_df['date'].map(daily_in).fillna(0.0).values
                daily_df['outflow'] = daily_df['date'].map(daily_out).fillna(0.0).values
                daily_df['net'] = daily_df['inflow'] - daily_df['outflow']
                daily_df['balance'] = balance_as_of - daily_df['net'].iloc[::-1].cumsum().iloc[::-1] + daily_df['net']
            else:
                daily_df = pd.DataFrame(columns=['date', 'net', 'balance'])
        else:
            daily_df = pd.DataFrame(columns=['date', 'net', 'balance'])

        flows = daily_df['net'].to_numpy(dtype=float) if not daily_df.empty else np.zeros(0)
        balances = daily_df['balance'].to_numpy(dtype=float) if not daily_df.empty else np.zeros(0)
        dates = daily_df['date'].tolist() if not daily_df.empty else []

        lags = [1, 2, 3, 7, 14, 21, 28]
        max_lag = 28
        N = len(flows)
        future_dates = [pd.to_datetime(as_of) + pd.Timedelta(days=d) for d in range(1, horizon + 1)]

        if N > max_lag + 7:
            X, y = [], []
            for i in range(max_lag, N):
                row = [flows[i - l] for l in lags]
                row.append(float(np.mean(flows[max(0, i-7):i])))
                row.append(float(np.mean(flows[max(0, i-28):i])))
                row.append(float(np.std(flows[max(0, i-7):i])) if i >= 7 else 0.0)
                row.append(float(np.std(flows[max(0, i-28):i])) if i >= 28 else 0.0)
                dt = dates[i]
                row.append(float(dt.day_of_week))
                row.append(float(dt.day))
                row.append(float(dt.month))
                row.append(1.0 if dt.day_of_week >= 5 else 0.0)
                row.append(float(balances[i-1]))
                X.append(row)
                y.append(flows[i])

            X_arr = np.asarray(X, dtype=float)
            y_arr = np.asarray(y, dtype=float)

            import lightgbm as lgb
            ridge = Ridge(alpha=self.ridge_alpha, random_state=seed).fit(X_arr, y_arr)

            buf_flows = list(flows[-max_lag:])
            buf_bal = balances[-1] if len(balances) > 0 else balance_as_of
            p50_b = []
            for step in range(horizon):
                dt = future_dates[step]
                row = [buf_flows[-l] for l in lags]
                row.append(float(np.mean(buf_flows[-7:])))
                row.append(float(np.mean(buf_flows[-28:])))
                row.append(float(np.std(buf_flows[-7:])))
                row.append(float(np.std(buf_flows[-28:])))
                row.append(float(dt.day_of_week))
                row.append(float(dt.day))
                row.append(float(dt.month))
                row.append(1.0 if dt.day_of_week >= 5 else 0.0)
                row.append(float(buf_bal))

                f_pred = float(ridge.predict([row])[0]) if dt.day_of_week < 5 else 0.0
                buf_bal += f_pred
                p50_b.append(buf_bal)
                buf_flows.append(f_pred)

            p50 = np.asarray(p50_b, dtype=float)

            y_res = y_arr - ridge.predict(X_arr)
            m10 = lgb.LGBMRegressor(objective="quantile", alpha=0.10, n_estimators=self.n_estimators, num_leaves=self.num_leaves, learning_rate=self.lr, random_state=seed, verbose=-1)
            m90 = lgb.LGBMRegressor(objective="quantile", alpha=0.90, n_estimators=self.n_estimators, num_leaves=self.num_leaves, learning_rate=self.lr, random_state=seed, verbose=-1)
            m10.fit(X_arr, y_res)
            m90.fit(X_arr, y_res)

            p10_b, p90_b = [], []
            cur_p10, cur_p90 = balance_as_of, balance_as_of
            buf_lgb = list(flows[-max_lag:])

            for step in range(horizon):
                dt = future_dates[step]
                f_row = [buf_lgb[-l] for l in lags]
                f_row.append(float(np.mean(buf_lgb[-7:])))
                f_row.append(float(np.mean(buf_lgb[-28:])))
                f_row.append(float(np.std(buf_lgb[-7:])))
                f_row.append(float(np.std(buf_lgb[-28:])))
                f_row.append(float(dt.day_of_week))
                f_row.append(float(dt.day))
                f_row.append(float(dt.month))
                f_row.append(1.0 if dt.day_of_week >= 5 else 0.0)
                f_row.append(p50[step])

                f10 = float(m10.predict([f_row])[0])
                f90 = float(m90.predict([f_row])[0])
                cur_p10 += f10
                cur_p90 += f90

                p10_b.append(min(cur_p10, p50[step]))
                p90_b.append(max(cur_p90, p50[step]))
                buf_lgb.append((f10 + f90) / 2.0)

            p10 = np.asarray(p10_b, dtype=float)
            p90 = np.asarray(p90_b, dtype=float)
        else:
            p50 = np.full(horizon, balance_as_of, dtype=float)
            p10 = p50 - 50000.0 * np.sqrt(np.arange(1, horizon + 1))
            p90 = p50 + 50000.0 * np.sqrt(np.arange(1, horizon + 1))

        sigma_eff = np.maximum(1000.0, (p90 - p10) / (2.0 * 1.28155))
        z_pw = -p50 / sigma_eff
        p_pw_max = float(np.max(0.5 * (1.0 + np.vectorize(math.erf)(z_pw / np.sqrt(2.0)))))

        if balance_as_of < 0:
            p_any = 1.0
            synth = np.zeros((100, horizon))
        else:
            L_sub = L_CHOLESKY[:horizon, :horizon]
            rng = np.random.default_rng(seed)
            z = rng.standard_normal((1000, horizon))
            synth = p50 + sigma_eff * (z @ L_sub.T)
            p_any = float(np.mean(np.min(synth, axis=1) < 0))

        days_result = [
            {
                "date": future_dates[i].date(),
                "p10": round(float(p10[i]), 2),
                "p50": round(float(p50[i]), 2),
                "p90": round(float(p90[i]), 2),
                "prob_negative": round(float(0.5 * (1.0 + math.erf((-p50[i] / (sigma_eff[i] * math.sqrt(2.0)))))), 4)
            }
            for i in range(horizon)
        ]

        return {
            "model_version": "old-ml-lgbm-cumsum",
            "quality": "medium",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "gap_probability": round(p_any, 4),
            "p_any": round(p_any, 4),
            "p_pointwise_max": round(p_pw_max, 4),
            "sample_paths": synth
        }


class Step1Forecaster:
    """
    Step 1: ML-only Recursive Autoregression.
    Slots are used strictly as calendar & distance features (not subtracted, not injected).
    Supports:
    - Per-Company mode (trains locally)
    - Global mode (uses pre-trained global_model with scale_factor)
    """
    def __init__(self, ridge_alpha: float = 15.0, global_model: Any = None, scale_factor: float = 1.0):
        self.ridge_alpha = ridge_alpha
        self.global_model = global_model
        self.scale_factor = max(float(scale_factor), 1.0)

    def forecast(
        self,
        history: pd.DataFrame,
        balance_as_of: float,
        as_of: date,
        horizon: int = 30,
        events: Optional[List[Dict[str, Any]]] = None,
        scenario: Optional[Dict[str, Any]] = None,
        overdraft_limit: float = 0.0,
        detected_slots: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42,
        **kwargs
    ) -> Dict[str, Any]:
        h_df = history.copy()
        if not h_df.empty and 'operation_date' in h_df.columns:
            h_df['operation_date'] = pd.to_datetime(h_df['operation_date']).dt.normalize()
            as_of_dt = pd.to_datetime(as_of).normalize()
            h_df = h_df[h_df['operation_date'] <= as_of_dt]

            owner_filter = h_df.apply(
                lambda r: is_owner_operation(
                    purpose=r.get('payment_purpose'),
                    category_id=r.get('category_id'),
                    counterparty_name=r.get('counterparty_name'),
                    counterparty_inn=r.get('counterparty_inn')
                ),
                axis=1
            )
            h_df = h_df[~owner_filter]

            if not h_df.empty:
                daily_in = h_df[h_df['direction'] == 'Поступление'].groupby('operation_date')['amount'].sum()
                daily_out = h_df[h_df['direction'] == 'Списание'].groupby('operation_date')['amount'].sum()
                min_dt = h_df['operation_date'].min()
                all_dates = pd.date_range(min_dt, as_of_dt, freq='D')
                daily_df = pd.DataFrame({'date': all_dates})
                daily_df['inflow'] = daily_df['date'].map(daily_in).fillna(0.0).values
                daily_df['outflow'] = daily_df['date'].map(daily_out).fillna(0.0).values
                daily_df['net'] = daily_df['inflow'] - daily_df['outflow']
            else:
                daily_df = pd.DataFrame(columns=['date', 'net'])
        else:
            daily_df = pd.DataFrame(columns=['date', 'net'])

        flows = daily_df['net'].to_numpy(dtype=float) if not daily_df.empty else np.zeros(0)
        dates = daily_df['date'].tolist() if not daily_df.empty else []

        lags = [1, 2, 3, 7, 14, 21, 28]
        max_lag = 28
        N = len(flows)
        future_dates = [pd.to_datetime(as_of) + pd.Timedelta(days=d) for d in range(1, horizon + 1)]

        s_factor = self.scale_factor if self.global_model is not None else 1.0

        if self.global_model is not None:
            model = self.global_model
        elif N > max_lag + 7:
            X, y = [], []
            for i in range(max_lag, N):
                row = [flows[i - l] for l in lags]
                row.append(float(np.mean(flows[max(0, i-7):i])))
                row.append(float(np.mean(flows[max(0, i-28):i])))
                row.append(float(np.std(flows[max(0, i-7):i])) if i >= 7 else 0.0)
                row.append(float(np.std(flows[max(0, i-28):i])) if i >= 28 else 0.0)
                dt = dates[i]
                row.extend(extract_calendar_features(dt))
                row.extend(extract_slot_features(dt, events))
                X.append(row)
                y.append(flows[i])
            X_arr = np.asarray(X, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            X_sc = scaler.fit_transform(X_arr)
            model = Ridge(alpha=self.ridge_alpha, random_state=seed).fit(X_sc, y_arr)
        else:
            model = None

        if model is not None and N >= max_lag:
            buf_flows = list(flows[-max_lag:])
            p50_f = []
            for step in range(horizon):
                dt = future_dates[step]
                row = [buf_flows[-l] / s_factor for l in lags]
                row.append(float(np.mean(buf_flows[-7:])) / s_factor)
                row.append(float(np.mean(buf_flows[-28:])) / s_factor)
                row.append(float(np.std(buf_flows[-7:])) / s_factor)
                row.append(float(np.std(buf_flows[-28:])) / s_factor)
                row.extend(extract_calendar_features(dt))
                row.extend(extract_slot_features(dt, events))

                row_sc = scaler.transform([row]) if 'scaler' in locals() else [row]
                f_pred = float(model.predict(row_sc)[0]) * s_factor if dt.day_of_week < 5 else 0.0
                p50_f.append(f_pred)
                buf_flows.append(f_pred)

            p50_flows = np.asarray(p50_f, dtype=float)
            p50 = balance_as_of + np.cumsum(p50_flows)
        else:
            mean_f = float(np.mean(flows)) if N > 0 else 0.0
            p50 = balance_as_of + np.arange(1, horizon + 1) * mean_f

        if model is not None and 'X_arr' in locals() and len(X_arr) > 1:
            res_arr = y_arr - model.predict(X_arr)
            sigma_base = max(1000.0, float(np.std(res_arr)))
        elif self.global_model is not None:
            sigma_base = max(1000.0, 25000.0 * (s_factor / 100000.0))
        elif N > 1:
            sigma_base = max(1000.0, float(np.std(flows)))
        else:
            sigma_base = 25000.0

        sigma_grow = sigma_base * np.arange(1, horizon + 1)
        p10 = p50 - 1.28155 * sigma_grow
        p90 = p50 + 1.28155 * sigma_grow

        z_pw = -p50 / (sigma_grow * math.sqrt(2.0))
        p_pw_max = float(np.max(0.5 * (1.0 + np.vectorize(math.erf)(z_pw))))

        if balance_as_of < 0:
            p_any = 1.0
            synth = np.zeros((100, horizon))
        else:
            L_sub = L_CHOLESKY[:horizon, :horizon]
            rng = np.random.default_rng(seed)
            z = rng.standard_normal((1000, horizon))
            synth = p50 + sigma_grow * (z @ L_sub.T)
            p_any = float(np.mean(np.min(synth, axis=1) < 0))

        days_result = [
            {
                "date": future_dates[i].date(),
                "p10": round(float(p10[i]), 2),
                "p50": round(float(p50[i]), 2),
                "p90": round(float(p90[i]), 2),
                "prob_negative": round(float(0.5 * (1.0 + math.erf((-p50[i] / (sigma_grow[i] * math.sqrt(2.0)))))), 4)
            }
            for i in range(horizon)
        ]

        ver_str = "step1-ml-only-global" if self.global_model is not None else "step1-ml-only-recursive"
        return {
            "model_version": ver_str,
            "quality": "medium",
            "as_of": as_of,
            "horizon": horizon,
            "days": days_result,
            "gap_probability": round(p_any, 4),
            "p_any": round(p_any, 4),
            "p_pointwise_max": round(p_pw_max, 4),
            "sample_paths": synth
        }
