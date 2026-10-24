import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_e2e_company_and_forecast():
    # 1. Company info
    res = client.get("/api/companies/C001")
    assert res.status_code == 200
    comp = res.json()
    assert comp["id"] == "C001"
    assert "last_balance" in comp

    # 2. Monte Carlo Forecast
    f_res = client.get("/api/companies/C001/forecast?horizon=30&model=monte-carlo")
    assert f_res.status_code == 200
    forecast = f_res.json()
    assert len(forecast["days"]) == 30
    assert "simulation_meta" in forecast
    assert forecast["simulation_meta"]["iterations"] == 1000

def test_e2e_analytics_and_slots():
    # 3. Analytics
    res = client.get("/api/companies/C001/analytics")
    assert res.status_code == 200
    an = res.json()
    assert "safety_runway_days" in an
    assert "total_inflow" in an
    assert "total_outflow" in an
    assert "fixed_monthly_burn" in an

    # 4. Slots CRUD
    s_res = client.get("/api/companies/C001/slots")
    assert s_res.status_code == 200

    create_res = client.post("/api/companies/C001/slots", json={
        "category_id": "cat_payroll",
        "typical_amount": 75000.0,
        "day_of_month": 15,
        "counterparty_name": "Тестовый ФОТ",
        "direction": "Списание"
    })
    assert create_res.status_code == 200
    slot = create_res.json()
    slot_id = slot["id"]

    del_res = client.delete(f"/api/slots/{slot_id}")
    assert del_res.status_code == 200

def test_e2e_integrations_and_sync():
    # 5. Integrations list
    res = client.get("/api/companies/C001/integrations")
    assert res.status_code == 200
    integrations = res.json()
    assert len(integrations) > 0

    # 6. Integration sync (with alias "1c")
    sync_res = client.post("/api/companies/C001/integrations/1c/sync")
    assert sync_res.status_code == 200
    data = sync_res.json()
    assert "events_added_this_run" in data

    # 7. Registry check
    reg_res = client.get("/api/integrations/registry/check?inn=7707083893")
    assert reg_res.status_code == 200
    assert "details" in reg_res.json()

def test_e2e_scenarios_and_alerts():
    # 8. Scenario comparison
    scen_res = client.get("/api/companies/C001/scenarios/scen_delay_client_C001/compare?horizon=30")
    assert scen_res.status_code == 200
    scen_data = scen_res.json()
    assert "comparison" in scen_data
    assert len(scen_data["comparison"]) == 30

    # 9. Alerts for C004 (cash gap company)
    a_res = client.get("/api/companies/C004/alerts")
    assert a_res.status_code == 200
    alerts = a_res.json()
    assert len(alerts) > 0
    assert len(alerts[0]["actions"]) >= 3

def test_e2e_export():
    # 10. Tax declaration export
    exp_res = client.get("/api/companies/C001/export/tax-declaration")
    assert exp_res.status_code == 200
    assert "text/csv" in exp_res.headers["content-type"]


def test_e2e_categories_crud():
    # 1. List categories
    res = client.get("/api/companies/C001/categories")
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) >= 10

    # 2. Create custom category
    create_res = client.post("/api/companies/C001/categories", json={
        "name": "Серверы и облако",
        "cashflow_role": "variable_out",
        "color": "#6366f1",
        "icon": "server"
    })
    assert create_res.status_code == 200
    new_cat = create_res.json()
    assert new_cat["name"] == "Серверы и облако"
    assert new_cat["id"].startswith("cat_")
    cat_id = new_cat["id"]

    # 3. Update (edit) category
    patch_res = client.patch(f"/api/companies/C001/categories/{cat_id}", json={
        "name": "Серверная инфраструктура",
        "color": "#4f46e5"
    })
    assert patch_res.status_code == 200
    updated_cat = patch_res.json()
    assert updated_cat["name"] == "Серверная инфраструктура"
    assert updated_cat["color"] == "#4f46e5"

    # 4. Delete category
    del_res = client.delete(f"/api/companies/C001/categories/{cat_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True
