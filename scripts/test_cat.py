# -*- coding: utf-8 -*-
import sys, csv
sys.stdout.reconfigure(encoding='utf-8')
from backend.core.categorizer import classify_operation

with open('data/all_operations.csv', 'r', encoding='utf-8-sig') as f:
    r = csv.DictReader(f, delimiter=';')
    for i in range(15):
        row = next(r)
        cat, conf, src = classify_operation(row['payment_purpose'], row['direction'], row['counterparty_name'], row['counterparty_inn'])
        print(f"{row['operation_id']}: {cat} (dir={row['direction']}, conf={conf}) | {row['payment_purpose'][:40]}")
