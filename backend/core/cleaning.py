import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Tuple, Dict, Any, List

def parse_operations_csv(filepath_or_buffer) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Parses and cleans bank statement CSV according to section 3.1:
    - Reads counterparty_inn as string preserving leading zeros (FR-1.2)
    - Deduplicates rows and counts duplicates (FR-1.3)
    - Detects gaps > 7 days and balance jumps (FR-1.4)
    - Recovers initial balance (FR-1.6)
    - Generates Quality Report (FR-1.8)
    """
    # Read with string dtype for INN and IDs
    df = pd.read_csv(
        filepath_or_buffer,
        sep=';',
        encoding='utf-8-sig',
        dtype={
            'company_id': str,
            'operation_id': str,
            'counterparty_inn': str,
            'counterparty_name': str,
            'payment_purpose': str,
            'direction': str,
        }
    )

    # Clean string columns
    for col in ['counterparty_inn', 'counterparty_name', 'payment_purpose', 'direction']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()

    # Convert amounts
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    df['balance_eod'] = pd.to_numeric(df['balance_eod'], errors='coerce').fillna(0.0)

    # Convert dates
    df['operation_date'] = pd.to_datetime(df['operation_date'], format='%Y-%m-%d', errors='coerce')
    df = df.dropna(subset=['operation_date'])
    df = df.sort_values(by=['operation_date', 'operation_id']).reset_index(drop=True)

    initial_count = len(df)

    # Deduplication: same date, amount, direction, counterparty_inn, payment_purpose
    dedup_cols = ['operation_date', 'amount', 'direction', 'counterparty_inn', 'payment_purpose']
    duplicate_mask = df.duplicated(subset=dedup_cols, keep='first')
    duplicate_count = int(duplicate_mask.sum())
    
    # Mark duplicates
    df['is_duplicate'] = duplicate_mask
    clean_df = df[~duplicate_mask].copy().reset_index(drop=True)

    # Quality Report Metrics
    missing_inn = int((clean_df['counterparty_inn'] == '').sum())
    missing_purpose = int((clean_df['payment_purpose'] == '').sum())

    # Daily aggregation to find gaps and balance jumps
    daily = clean_df.groupby('operation_date').agg(
        inflow=('amount', lambda x: clean_df.loc[x.index][clean_df.loc[x.index, 'direction'] == 'Поступление']['amount'].sum()),
        outflow=('amount', lambda x: clean_df.loc[x.index][clean_df.loc[x.index, 'direction'] == 'Списание']['amount'].sum()),
        last_balance=('balance_eod', 'last'),
        op_count=('amount', 'count')
    ).reset_index().sort_values('operation_date')

    # Detect gaps > 7 days
    daily['prev_date'] = daily['operation_date'].shift(1)
    daily['date_diff'] = (daily['operation_date'] - daily['prev_date']).dt.days
    gaps_mask = daily['date_diff'] > 7
    gaps = []
    for _, row in daily[gaps_mask].iterrows():
        gaps.append({
            'from_date': row['prev_date'].strftime('%Y-%m-%d'),
            'to_date': row['operation_date'].strftime('%Y-%m-%d'),
            'days': int(row['date_diff'])
        })

    # Detect balance jumps
    # balance_eod should equal prev_balance + inflow - outflow
    daily['prev_balance'] = daily['last_balance'].shift(1)
    daily['expected_balance'] = daily['prev_balance'] + daily['inflow'] - daily['outflow']
    daily['balance_diff'] = (daily['last_balance'] - daily['expected_balance']).abs()
    
    # Exclude the first day (no previous balance)
    jumps_mask = (daily['balance_diff'] > 0.05) & (daily['prev_balance'].notna())
    balance_jumps_count = int(jumps_mask.sum())

    # Count days with negative balance
    neg_balance_days = int((daily['last_balance'] < 0).sum())

    # Calculate starting balance before first day
    if len(daily) > 0:
        first_day = daily.iloc[0]
        initial_balance = float(first_day['last_balance'] - first_day['inflow'] + first_day['outflow'])
        first_date = daily['operation_date'].min().strftime('%Y-%m-%d')
        last_date = daily['operation_date'].max().strftime('%Y-%m-%d')
    else:
        initial_balance = 0.0
        first_date = None
        last_date = None

    # Calculate overall quality score (0..100)
    score = 100.0
    warnings = []
    if duplicate_count > 0:
        score -= min(10.0, duplicate_count * 0.5)
        warnings.append(f"Обнаружено {duplicate_count} дубликатов операций (удалены).")
    if len(gaps) > 0:
        score -= min(20.0, len(gaps) * 5.0)
        warnings.append(f"Обнаружено {len(gaps)} пропусков данных более 7 дней.")
    if balance_jumps_count > 0:
        score -= min(25.0, balance_jumps_count * 2.0)
        warnings.append(f"Обнаружено {balance_jumps_count} скачков остатка без операций.")
    if missing_inn > 0:
        pct = (missing_inn / max(1, len(clean_df))) * 100
        if pct > 10:
            score -= 10.0
            warnings.append(f"У {pct:.1f}% операций не указан ИНН контрагента.")
    if neg_balance_days > 0:
        warnings.append(f"Остаток был отрицательным {neg_balance_days} дней (использовался овердрафт).")

    score = max(10.0, min(100.0, round(score, 1)))

    quality_report = {
        'initial_count': initial_count,
        'clean_count': len(clean_df),
        'duplicate_rows_count': duplicate_count,
        'missing_inn_count': missing_inn,
        'missing_purpose_count': missing_purpose,
        'gaps_longer_than_7_days': gaps,
        'balance_jumps_count': balance_jumps_count,
        'negative_balance_days_count': neg_balance_days,
        'initial_balance': initial_balance,
        'first_date': first_date,
        'last_date': last_date,
        'quality_score': score,
        'warnings': warnings
    }

    return clean_df, quality_report
