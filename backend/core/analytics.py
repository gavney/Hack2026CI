import pandas as pd
import numpy as np
from typing import Dict, Any, List
from backend.core.categorizer import CATEGORY_LOOKUP

def calculate_analytics(df_ops: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes cashflow analytics according to section 3.11:
    - Inflow & outflow structure by category
    - Monthly dynamics
    - Owner money breakdown
    - Top counterparties & revenue concentration
    - Safety buffer / runway
    """
    if df_ops.empty:
        return {
            "total_inflow": 0.0,
            "total_outflow": 0.0,
            "net_flow": 0.0,
            "inflow_categories": [],
            "outflow_categories": [],
            "monthly_dynamics": [],
            "owner_draw_summary": {},
            "top_counterparties": [],
            "concentration_warning": None,
            "safety_runway_days": 0
        }

    df = df_ops.copy()
    
    # Exclude internal account transfers from revenue/expense metrics (FR-2.14)
    analysis_df = df[df['category_id'] != 'cat_transfer_own'].copy()

    inflows_df = analysis_df[analysis_df['direction'] == 'Поступление']
    outflows_df = analysis_df[analysis_df['direction'] == 'Списание']

    total_inflow = float(inflows_df['amount'].sum())
    total_outflow = float(outflows_df['amount'].sum())
    net_flow = total_inflow - total_outflow

    # Category breakdowns
    def get_cat_summary(sub_df, total):
        res = []
        if total <= 0:
            return res
        grp = sub_df.groupby('category_id')['amount'].sum().reset_index()
        grp = grp.sort_values('amount', ascending=False)
        for _, r in grp.iterrows():
            cid = r['category_id']
            c_info = CATEGORY_LOOKUP.get(cid, {})
            c_name = c_info.get('name', cid)
            c_color = c_info.get('color', '#64748b')
            amt = float(r['amount'])
            pct = (amt / total) * 100
            res.append({
                "category_id": cid,
                "name": c_name,
                "amount": round(amt, 2),
                "percent": round(pct, 1),
                "color": c_color,
                "per_100_rubles": round((amt / total) * 100, 1)  # Section 3.11: на каждые 100 руб
            })
        return res

    inflow_cats = get_cat_summary(inflows_df, total_inflow)
    outflow_cats = get_cat_summary(outflows_df, total_outflow)

    # Monthly dynamics
    analysis_df['year_month'] = pd.to_datetime(analysis_df['operation_date']).dt.strftime('%Y-%m')
    monthly = analysis_df.groupby(['year_month', 'direction'])['amount'].sum().unstack(fill_value=0.0).reset_index()
    monthly_dynamics = []
    for _, r in monthly.iterrows():
        inf = float(r.get('Поступление', 0.0))
        outf = float(r.get('Списание', 0.0))
        monthly_dynamics.append({
            "month": str(r['year_month']),
            "inflow": round(inf, 2),
            "outflow": round(outf, 2),
            "net": round(inf - outf, 2)
        })

    # Owner money breakdown (FR-11.6)
    owner_draw_sum = float(outflows_df[outflows_df['category_id'] == 'cat_owner_draw']['amount'].sum())
    business_retained = max(0.0, net_flow - owner_draw_sum) if net_flow > 0 else 0.0
    owner_summary = {
        "withdrawn_by_owner": round(owner_draw_sum, 2),
        "retained_in_business": round(business_retained, 2),
        "share_of_net": round((owner_draw_sum / max(1.0, net_flow)) * 100, 1) if net_flow > 0 else 0.0
    }

    # Top counterparties & revenue concentration warning (FR-11.7)
    top_counterparties = []
    concentration_warning = None
    if total_inflow > 0:
        c_grp = inflows_df.groupby(['counterparty_inn', 'counterparty_name'])['amount'].sum().reset_index()
        c_grp = c_grp.sort_values('amount', ascending=False)
        for _, r in c_grp.head(5).iterrows():
            amt = float(r['amount'])
            pct = (amt / total_inflow) * 100
            name = str(r['counterparty_name']) or "Контрагент без названия"
            inn = str(r['counterparty_inn'])
            top_counterparties.append({
                "inn": inn,
                "name": name,
                "amount": round(amt, 2),
                "percent": round(pct, 1)
            })
        
        # Check if top client > 25%
        if top_counterparties and top_counterparties[0]['percent'] > 25.0:
            top_c = top_counterparties[0]
            concentration_warning = (
                f"Высокая зависимость: контрагент «{top_c['name']}» обеспечивает {top_c['percent']:.1f}% всей вашей выручки. "
                f"Задержка оплаты с его стороны создаст немедленный кассовый разрыв."
            )

    # Safety runway days (FR-11.4)
    # Fixed monthly obligations (payroll, rent, taxes, loans)
    fixed_roles = ['regular_out', 'tax']
    fixed_cats = [c["id"] for c in CATEGORY_LOOKUP.values() if c["cashflow_role"] in fixed_roles]
    fixed_monthly = float(outflows_df[outflows_df['category_id'].isin(fixed_cats)]['amount'].sum()) / max(1, len(monthly_dynamics))
    daily_fixed = fixed_monthly / 30.0

    last_balance = float(df['balance_eod'].iloc[-1]) if not df.empty else 0.0
    runway_days = int(last_balance / max(100.0, daily_fixed)) if last_balance > 0 else 0

    return {
        "total_inflow": round(total_inflow, 2),
        "total_outflow": round(total_outflow, 2),
        "net_flow": round(net_flow, 2),
        "inflow_categories": inflow_cats,
        "outflow_categories": outflow_cats,
        "monthly_dynamics": monthly_dynamics,
        "owner_draw_summary": owner_summary,
        "top_counterparties": top_counterparties,
        "concentration_warning": concentration_warning,
        "safety_runway_days": runway_days,
        "fixed_monthly_burn": round(fixed_monthly, 2)
    }
