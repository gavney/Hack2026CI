import io
import pandas as pd
from backend.core.cleaning import parse_operations_csv

def test_inn_string_leading_zeros():
    csv_data = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C001;op1;2025-01-10;1000.00;Поступление;0098765432;ООО Тест;Оплата по счету;1000.00"""
    df, qr = parse_operations_csv(io.StringIO(csv_data))
    assert df['counterparty_inn'].iloc[0] == "0098765432"
    assert isinstance(df['counterparty_inn'].iloc[0], str)

def test_deduplication():
    csv_data = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C001;op1;2025-01-10;1000.00;Поступление;0012345678;ООО Тест;Оплата по счету;1000.00
C001;op2;2025-01-10;1000.00;Поступление;0012345678;ООО Тест;Оплата по счету;1000.00"""
    df, qr = parse_operations_csv(io.StringIO(csv_data))
    assert len(df) == 1
    assert qr['duplicate_rows_count'] == 1

def test_initial_balance_recovery():
    # Initial balance = balance_eod - inflow + outflow = 5000 - 3000 + 1000 = 3000
    csv_data = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C001;op1;2025-01-10;3000.00;Поступление;0012345678;ООО Тест;Оплата по счету;5000.00
C001;op2;2025-01-10;1000.00;Списание;0012345678;ООО Поставщик;Оплата товаров;5000.00"""
    df, qr = parse_operations_csv(io.StringIO(csv_data))
    assert qr['initial_balance'] == 3000.0
