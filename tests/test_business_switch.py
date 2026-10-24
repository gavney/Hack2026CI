import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models import User, Company, UserCompany
from backend.core.security import create_access_token

client = TestClient(app)

def test_switch_business_persistence():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@centroinvest.ru").first()
        assert user is not None

        token = create_access_token({"sub": user.id})
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Check initial me
        me_res = client.get("/api/auth/me", headers=headers)
        assert me_res.status_code == 200
        initial_comp = me_res.json()["company"]["id"]

        # 2. Switch to C004
        switch_res = client.post("/api/auth/switch-company/C004", headers=headers)
        assert switch_res.status_code == 200
        assert switch_res.json()["company_id"] == "C004"

        # 3. Simulate page reload (/api/auth/me)
        me_res2 = client.get("/api/auth/me", headers=headers)
        assert me_res2.status_code == 200
        assert me_res2.json()["company"]["id"] == "C004"

        # 4. Switch back
        switch_back = client.post(f"/api/auth/switch-company/{initial_comp}", headers=headers)
        assert switch_back.status_code == 200
        assert switch_back.json()["company_id"] == initial_comp

        me_res3 = client.get("/api/auth/me", headers=headers)
        assert me_res3.status_code == 200
        assert me_res3.json()["company"]["id"] == initial_comp
    finally:
        db.close()
