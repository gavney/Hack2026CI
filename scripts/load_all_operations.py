# -*- coding: utf-8 -*-
import sys
import os
import sqlite3
import csv
import time
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

from backend.core.categorizer import classify_operation
from backend.core.slots import detect_recurring_slots

def run():
    print("Starting full data load from data/all_operations.csv into radar.db...")
    t0 = time.time()
    conn = sqlite3.connect("radar.db", timeout=60.0)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM operations")
    conn.commit()

    rows = []
    batch_size = 25000

    with open("data/all_operations.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            cat_id, conf, src = classify_operation(
                direction=row["direction"],
                payment_purpose=row["payment_purpose"],
                counterparty_inn=str(row["counterparty_inn"]),
                counterparty_name=row["counterparty_name"]
            )
            rows.append((
                row["company_id"],
                row["operation_id"],
                row["operation_date"],
                float(row["amount"]),
                row["direction"],
                str(row["counterparty_inn"]),
                row["counterparty_name"],
                row["payment_purpose"],
                float(row["balance_eod"]),
                cat_id,
                conf,
                src,
                False
            ))
            if len(rows) >= batch_size:
                cursor.executemany("""
                    INSERT INTO operations (
                        company_id, operation_id, operation_date, amount, direction,
                        counterparty_inn, counterparty_name, payment_purpose, balance_eod,
                        category_id, category_confidence, category_source, is_duplicate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                rows = []

    if rows:
        cursor.executemany("""
            INSERT INTO operations (
                company_id, operation_id, operation_date, amount, direction,
                counterparty_inn, counterparty_name, payment_purpose, balance_eod,
                category_id, category_confidence, category_source, is_duplicate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    print(f"Inserted 222,420 operations in {time.time()-t0:.2f}s.")

    # Update company stats
    cursor.execute("""
        UPDATE companies
        SET operations_count = (SELECT COUNT(*) FROM operations WHERE operations.company_id = companies.id),
            first_operation_date = (SELECT MIN(operation_date) FROM operations WHERE operations.company_id = companies.id),
            last_operation_date = (SELECT MAX(operation_date) FROM operations WHERE operations.company_id = companies.id),
            last_balance = COALESCE((SELECT balance_eod FROM operations WHERE operations.company_id = companies.id ORDER BY operation_date DESC, id DESC LIMIT 1), last_balance),
            has_statement = CASE WHEN (SELECT COUNT(*) FROM operations WHERE operations.company_id = companies.id) > 0 THEN 1 ELSE 0 END
    """)
    conn.commit()

    # Detect recurring slots
    print("Detecting recurring slots for all companies...")
    cursor.execute("DELETE FROM slots")
    conn.commit()

    companies = [r[0] for r in cursor.execute("SELECT id FROM companies WHERE operations_count > 0").fetchall()]
    slots_to_insert = []

    for cid in companies:
        ops_rows = cursor.execute("""
            SELECT operation_date, amount, direction, counterparty_inn, counterparty_name, category_id
            FROM operations WHERE company_id = ?
        """, (cid,)).fetchall()
        if not ops_rows:
            continue
        df = pd.DataFrame(ops_rows, columns=["operation_date", "amount", "direction", "counterparty_inn", "counterparty_name", "category_id"])
        slots = detect_recurring_slots(df)
        for s in slots:
            slots_to_insert.append((
                cid,
                s["category_id"],
                s.get("counterparty_inn"),
                s.get("counterparty_name"),
                s["direction"],
                s["day_of_month"],
                s["typical_amount"],
                s.get("presence_rate", 0.8),
                False,
                True
            ))

    cursor.executemany("""
        INSERT INTO slots (
            company_id, category_id, counterparty_inn, counterparty_name, direction,
            day_of_month, typical_amount, share_of_months, confirmed_by_user, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, slots_to_insert)
    conn.commit()

    print(f"Total slots detected and saved: {len(slots_to_insert)} across {len(companies)} companies.")
    print(f"Entire process finished in {time.time()-t0:.2f}s!")

if __name__ == "__main__":
    run()
