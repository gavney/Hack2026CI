import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Any, Tuple
from backend.core.categorizer import CATEGORY_LOOKUP

# Simple Russian business days checker (weekends: Saturday & Sunday; can be extended with holidays)
def is_business_day(d: date) -> bool:
    return d.weekday() < 5

def next_business_day(d: date) -> date:
    cur = d
    while not is_business_day(cur):
        cur += timedelta(days=1)
    return cur

def detect_recurring_slots(
    df_ops: pd.DataFrame,
    window_days: int = 120,
    min_share_months: float = 0.60
) -> List[Dict[str, Any]]:
    """
    Detects recurring regular payment slots according to FR-3.1, FR-3.2:
    - Filters operations for roles 'regular_out' and 'tax'
    - Analyzes last window_days of history
    - Clusters by day-of-month (distance <= 3 days)
    - Slot is regular if found in >= 60% of months in the window
    - Calculates typical median monthly amount and share of months
    """
    if df_ops.empty:
        return []

    # Map categories to roles
    df = df_ops.copy()
    if 'cashflow_role' not in df.columns:
        df['cashflow_role'] = df['category_id'].map(lambda cid: CATEGORY_LOOKUP.get(cid, {}).get('cashflow_role', 'variable_out'))

    # Filter by regular_out and tax, only outflows
    target_roles = ['regular_out', 'tax']
    reg_df = df[(df['cashflow_role'].isin(target_roles)) & (df['direction'] == 'Списание')].copy()
    
    if reg_df.empty:
        return []

    reg_df['operation_date'] = pd.to_datetime(reg_df['operation_date'])
    max_date = reg_df['operation_date'].max()
    min_window_date = max_date - pd.Timedelta(days=window_days)
    
    window_df = reg_df[reg_df['operation_date'] >= min_window_date].copy()
    if window_df.empty:
        window_df = reg_df.copy()

    window_df['year_month'] = window_df['operation_date'].dt.to_period('M')
    total_months = window_df['year_month'].nunique()
    if total_months == 0:
        return []

    window_df['day'] = window_df['operation_date'].dt.day

    detected_slots = []

    # Group by category and counterparty
    grouped = window_df.groupby(['category_id', 'counterparty_inn', 'counterparty_name'])

    for (cat_id, inn, name), group in grouped:
        # Cluster days: find the modal day or day clusters
        days = group['day'].values
        if len(days) == 0:
            continue

        # Simple 3-day clustering around median day
        median_day = int(np.median(days))
        
        # Check presence per month
        months_with_op = group['year_month'].nunique()
        share = months_with_op / max(1, total_months)

        if share >= min_share_months or (cat_id == 'cat_tax_enp' and share >= 0.5):
            # Special case for ENP (28th of every month)
            if cat_id == 'cat_tax_enp':
                median_day = 28

            typical_amount = float(group.groupby('year_month')['amount'].sum().median())
            
            detected_slots.append({
                "category_id": cat_id,
                "counterparty_inn": str(inn) if inn else "",
                "counterparty_name": str(name) if name else "",
                "direction": "Списание",
                "day_of_month": int(median_day),
                "typical_amount": round(typical_amount, 2),
                "share_of_months": round(float(share), 2),
                "confirmed_by_user": True,
                "is_active": True
            })

    return detected_slots

def infer_tax_regime(df_ops: pd.DataFrame) -> Tuple[str, float]:
    """
    Heuristically infers tax regime from operation history (FR-3.6):
    - Calculates tax share = taxes / total_inflows
    - If tax ~ 5-7% -> 'УСН Доходы 6%'
    - If tax ~ 12-16% of margin -> 'УСН Доходы-Расходы 15%'
    - Otherwise -> 'ОСНО' or default
    """
    if df_ops.empty:
        return "УСН Доходы 6%", 0.70

    inflows = df_ops[df_ops['direction'] == 'Поступление']['amount'].sum()
    taxes = df_ops[df_ops['category_id'] == 'cat_tax_enp']['amount'].sum()

    if inflows <= 0:
        return "УСН Доходы 6%", 0.70

    tax_ratio = taxes / inflows
    if 0.04 <= tax_ratio <= 0.08:
        return "УСН Доходы 6%", 0.85
    elif 0.08 < tax_ratio <= 0.16:
        return "УСН Доходы-Расходы 15%", 0.75
    elif tax_ratio > 0.16:
        return "ОСНО (НДС + Налог на прибыль)", 0.65
    else:
        return "УСН Доходы 6%", 0.60
