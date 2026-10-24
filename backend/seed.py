import os
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from backend.database import SessionLocal, engine, Base
from backend.models import Company, Category, Operation, Slot, IntegrationSource, Scenario, User, UserCompany
from backend.core.security import hash_password
from backend.core.categorizer import STANDARD_CATEGORIES, classify_operation
from backend.core.cleaning import parse_operations_csv
from backend.core.slots import detect_recurring_slots, infer_tax_regime
from backend.routers.integrations import DEFAULT_INTEGRATION_CONFIGS
from backend.routers.scenarios import DEFAULT_SCENARIOS

def seed_database(limit_companies_statements: int = 15):
    """
    Seeds database:
    - Standard categories
    - All companies from companies.csv
    - Statements for companies with cleaning, categorization, and slot detection
    - Default integrations and scenarios
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("1. Seeding standard categories...")
    for sc in STANDARD_CATEGORIES:
        existing = db.query(Category).filter(Category.id == sc["id"]).first()
        if not existing:
            cat = Category(
                id=sc["id"],
                name=sc["name"],
                cashflow_role=sc["cashflow_role"],
                color=sc["color"],
                icon=sc["icon"],
                status="confirmed"
            )
            db.add(cat)
    db.commit()

    print("2. Seeding companies from companies.csv...")
    comp_csv = os.path.join("data", "companies.csv")
    if os.path.exists(comp_csv):
        df_comp = pd.read_csv(comp_csv, sep=';', encoding='utf-8-sig', dtype=str)
        for _, row in df_comp.iterrows():
            cid = str(row['company_id'])
            existing = db.query(Company).filter(Company.id == cid).first()
            if not existing:
                comp = Company(
                    id=cid,
                    name=str(row['company_name']),
                    inn=str(row['company_inn']),  # Preserving leading zeros as string
                    legal_form=str(row['legal_form']),
                    industry=str(row['industry']),
                    first_operation_date=pd.to_datetime(row['first_operation_date']).date() if pd.notna(row['first_operation_date']) else None,
                    last_operation_date=pd.to_datetime(row['last_operation_date']).date() if pd.notna(row['last_operation_date']) else None,
                    operations_count=int(row['operations_count']) if pd.notna(row['operations_count']) else 0,
                    overdraft_limit=0.0,
                    tax_regime="УСН Доходы 6%"
                )
                db.add(comp)
        db.commit()
        print(f"Loaded {len(df_comp)} companies.")

    print(f"3. Ingesting statements for first {limit_companies_statements} companies...")
    stmt_dir = os.path.join("data", "statements")
    if os.path.exists(stmt_dir):
        files = sorted([f for f in os.listdir(stmt_dir) if f.endswith(".csv")])
        for filename in files[:limit_companies_statements]:
            cid = filename.replace(".csv", "")
            comp = db.query(Company).filter(Company.id == cid).first()
            if not comp:
                continue

            # Check if operations already loaded
            existing_ops_count = db.query(Operation).filter(Operation.company_id == cid).count()
            if existing_ops_count > 0:
                print(f"Company {cid} already has {existing_ops_count} operations, skipping.")
                continue

            file_path = os.path.join(stmt_dir, filename)
            clean_df, qr = parse_operations_csv(file_path)

            comp.data_quality_score = qr["quality_score"]

            # Classify operations
            cat_list = []
            for _, r in clean_df.iterrows():
                cat_id, conf, src = classify_operation(
                    direction=r['direction'],
                    payment_purpose=r['payment_purpose'],
                    counterparty_inn=r['counterparty_inn'],
                    counterparty_name=r['counterparty_name']
                )
                cat_list.append((cat_id, conf, src))

            # Infer tax regime
            clean_df['category_id'] = [c[0] for c in cat_list]
            regime, conf = infer_tax_regime(clean_df)
            comp.tax_regime = regime

            # Bulk insert operations
            db_ops = []
            for idx, r in clean_df.iterrows():
                cat_id, conf, src = cat_list[idx]
                db_ops.append(Operation(
                    company_id=cid,
                    operation_id=str(r.get('operation_id', f'op_{idx}')),
                    operation_date=r['operation_date'].date(),
                    amount=float(r['amount']),
                    direction=str(r['direction']),
                    counterparty_inn=str(r['counterparty_inn']) if r['counterparty_inn'] else "",
                    counterparty_name=str(r['counterparty_name']),
                    payment_purpose=str(r['payment_purpose']),
                    balance_eod=float(r['balance_eod']),
                    category_id=cat_id,
                    category_confidence=conf,
                    category_source=src,
                    is_duplicate=bool(r.get('is_duplicate', False))
                ))
            db.bulk_save_objects(db_ops)

            if len(clean_df) > 0:
                comp.last_balance = float(clean_df.iloc[-1]['balance_eod'])
                comp.operations_count = len(clean_df)

            # Detect recurring slots (FR-3.1)
            slots = detect_recurring_slots(clean_df)
            for s in slots:
                db_slot = Slot(
                    company_id=cid,
                    category_id=s["category_id"],
                    counterparty_inn=s["counterparty_inn"],
                    counterparty_name=s["counterparty_name"],
                    direction=s["direction"],
                    day_of_month=s["day_of_month"],
                    typical_amount=s["typical_amount"],
                    share_of_months=s["share_of_months"],
                    confirmed_by_user=True,
                    is_active=True
                )
                db.add(db_slot)

            # Seed default integrations
            for dic in DEFAULT_INTEGRATION_CONFIGS:
                src = IntegrationSource(
                    company_id=cid,
                    adapter_name=dic["adapter_name"],
                    display_name=dic["display_name"],
                    description=dic["description"],
                    status=dic["status"],
                    events_added=dic["events_added"],
                    last_sync_at=datetime.utcnow()
                )
                db.add(src)

            # Seed default scenarios
            for ds in DEFAULT_SCENARIOS:
                sc = Scenario(
                    id=f"{ds['id']}_{cid}",
                    company_id=cid,
                    name=ds["name"],
                    scenario_type=ds["scenario_type"],
                    params=ds["params"]
                )
                db.add(sc)

            db.commit()
            print(f"Company {cid}: ingested {len(clean_df)} clean operations, {len(slots)} slots. Tax: {regime}")

    print("4. Seeding default demo accounts...")
    # Demo Owner (linked to C001 and C004)
    demo_user = db.query(User).filter(User.email == "demo@centroinvest.ru").first()
    if not demo_user:
        demo_user = User(
            id="usr_demo_01",
            email="demo@centroinvest.ru",
            password_hash=hash_password("demo123"),
            full_name="Демо Предприниматель",
            role="owner",
            company_id="C001",
            is_active=True
        )
        db.add(demo_user)
        db.commit()

        # Link to C001 (default) and C004
        for cid, is_def in [("C001", True), ("C004", False)]:
            comp_exists = db.query(Company).filter(Company.id == cid).first()
            if comp_exists:
                uc = UserCompany(
                    user_id=demo_user.id,
                    company_id=cid,
                    role="owner",
                    is_default=is_def
                )
                db.add(uc)
        db.commit()
        print("Demo owner account seeded: demo@centroinvest.ru / demo123 (C001, C004)")

    # Bank Manager (has unrestricted access to all businesses)
    manager_user = db.query(User).filter(User.email == "manager@centroinvest.ru").first()
    if not manager_user:
        manager_user = User(
            id="usr_manager_01",
            email="manager@centroinvest.ru",
            password_hash=hash_password("manager123"),
            full_name="Кредитный Офицер Центр-Инвест",
            role="bank_manager",
            company_id="C001",
            is_active=True
        )
        db.add(manager_user)
        db.commit()
        print("Bank manager account seeded: manager@centroinvest.ru / manager123 (role: bank_manager)")

    print("5. Pre-warming alerts and forecasts for demo companies...")
    from backend.routers.forecast import get_company_forecast
    for cid in ["C001", "C004"]:
        try:
            get_company_forecast(cid, horizon=30, model="monte-carlo", db=db)
        except Exception as e:
            print(f"Notice: pre-warming forecast for {cid}: {e}")

    db.close()
    print("Seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
