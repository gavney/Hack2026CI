import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_counterparties_discovery_and_check():
    # 1. Fetch counterparties for C001 (auto-discovery)
    res = client.get("/api/companies/C001/counterparties")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first_cp = data[0]
    assert "inn" in first_cp
    assert "name" in first_cp
    assert "role" in first_cp
    assert "include_in_forecast" in first_cp

    # 2. Check FNS (nalogbi + check) for first counterparty
    check_res = client.post(f"/api/companies/C001/counterparties/{first_cp['inn']}/check")
    assert check_res.status_code == 200
    checked_cp = check_res.json()
    assert "risk_level" in checked_cp
    assert checked_cp["risk_level"] in ["green", "yellow", "red"]
    assert "reliability_score" in checked_cp
    assert 0 <= checked_cp["reliability_score"] <= 100
    assert "has_blocks" in checked_cp
    assert "positive_factors" in checked_cp
    assert "negative_factors" in checked_cp

    # 3. Toggle forecast checkbox
    toggle_res = client.patch(
        f"/api/companies/C001/counterparties/{first_cp['inn']}/toggle-forecast",
        json={"include_in_forecast": False}
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["include_in_forecast"] is False

    # 4. Create custom counterparty with FNS check
    new_res = client.post(
        "/api/companies/C001/counterparties",
        json={"inn": "7707083893", "name": "ООО «Тест Контрагент»", "role": "payer"}
    )
    assert new_res.status_code == 200
    new_cp = new_res.json()
    assert new_cp["inn"] == "7707083893"
    assert ("СБЕРБАНК" in new_cp["name"]) or (new_cp["name"] == "ООО «Тест Контрагент»")
    assert "reliability_score" in new_cp
