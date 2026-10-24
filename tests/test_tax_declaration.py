import io
from datetime import date
import pytest
import pymupdf as fitz
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Company, Operation, User
from backend.database import SessionLocal
from backend.core.security import create_access_token
from backend.core.tax_declaration_pdf import (
    generate_tax_declaration_pdf,
    get_company_tax_declaration_data
)


def test_generate_tax_declaration_pdf_usn_6():
    """Проверка генерации 3-страничного официального бланка УСН 6% (КНД 1152017)."""
    data = {
        "inn": "7707083893",
        "kpp": "773601001",
        "company_name": "ООО ТЕХНОЛОГИИ БУДУЩЕГО",
        "year": "2025",
        "correction_num": "0",
        "ifns_code": "7736",
        "oktmo": "45300000",
        "tax_object": "1",
        "phone": "+7 999 123-45-67",
        "rate": 6.0,
        "income_q1": 1000000,
        "income_q2": 2500000,
        "income_q3": 4000000,
        "income_year": 6000000,
        "tax_q1": 60000,
        "tax_q2": 150000,
        "tax_q3": 240000,
        "tax_year": 360000,
        "due_q1": 60000,
        "due_q2": 90000,
        "due_q3": 90000,
        "due_year": 120000
    }

    pdf_bytes = generate_tax_declaration_pdf(data)
    assert len(pdf_bytes) > 10000
    assert pdf_bytes.startswith(b"%PDF-")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 3

    # Проверка текста на страницах
    p1_text = doc[0].get_text()
    assert "1152017" in p1_text or "0301 6015" in p1_text

    p2_text = doc[1].get_text()
    assert "0301 6022" in p2_text or "1.1" in p2_text

    p3_text = doc[2].get_text()
    assert "0301 6046" in p3_text or "2.1.1" in p3_text


def test_generate_tax_declaration_pdf_usn_15():
    """Проверка генерации бланка УСН 15% (Доходы минус расходы) с штрихкодами 6039 и 6084."""
    data = {
        "inn": "616400000001",  # 12 digits (ИП)
        "kpp": "",
        "company_name": "ИП ПЕТРОВ ПЕТР ПЕТРОВИЧ",
        "year": "2025",
        "tax_object": "2",
        "rate": 15.0,
        "income_q1": 500000,
        "income_q2": 1200000,
        "income_q3": 2000000,
        "income_year": 3000000,
        "expense_q1": 300000,
        "expense_q2": 700000,
        "expense_q3": 1200000,
        "expense_year": 1800000,
        "tax_q1": 30000,
        "tax_q2": 75000,
        "tax_q3": 120000,
        "tax_year": 180000,
        "min_tax": 30000,
        "due_q1": 30000,
        "due_q2": 45000,
        "due_q3": 45000,
        "due_year": 60000
    }

    pdf_bytes = generate_tax_declaration_pdf(data)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 3

    p2_text = doc[1].get_text()
    assert "0301 6039" in p2_text or "1.2" in p2_text

    p3_text = doc[2].get_text()
    assert "0301 6084" in p3_text or "2.2" in p3_text


def test_get_company_tax_declaration_data():
    """Проверка расчета нарастающего итога по операциям из базы."""
    comp = Company(id="decl_comp_test", name="ООО Ромашка", inn="7700112233", tax_regime="УСН Доходы 6%", legal_form="ООО")
    ops = [
        Operation(operation_date=date(2025, 2, 10), amount=200000.0, direction="Поступление"),
        Operation(operation_date=date(2025, 5, 15), amount=300000.0, direction="Поступление"),
        Operation(operation_date=date(2025, 8, 20), amount=400000.0, direction="Поступление"),
        Operation(operation_date=date(2025, 11, 25), amount=500000.0, direction="Поступление"),
        Operation(operation_date=date(2025, 4, 1), amount=100000.0, direction="Списание"),
    ]

    res = get_company_tax_declaration_data(comp, ops, year=2025)
    # Нарастающий итог доходов:
    # Q1: 200,000
    # Q2: 200k + 300k = 500,000
    # Q3: 500k + 400k = 900,000
    # Year: 900k + 500k = 1,400,000
    assert res["income_q1"] == 200000
    assert res["income_q2"] == 500000
    assert res["income_q3"] == 900000
    assert res["income_year"] == 1400000

    # Налог 6%:
    # Q1: 12,000 -> due_q1 = 12,000
    # Q2: 30,000 -> due_q2 = 30k - 12k = 18,000
    # Q3: 54,000 -> due_q3 = 54k - 30k = 24,000
    # Year: 84,000 -> due_year = 84k - 54k = 30,000
    assert res["tax_q1"] == 12000
    assert res["tax_q2"] == 30000
    assert res["tax_q3"] == 54000
    assert res["tax_year"] == 84000
    assert res["due_q1"] == 12000
    assert res["due_q2"] == 18000
    assert res["due_q3"] == 24000
    assert res["due_year"] == 30000


def test_api_tax_declaration_endpoints():
    """Тестирование эндпоинтов GET /data и POST /generate-pdf."""
    client = TestClient(app)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@centroinvest.ru").first()
        assert user is not None
        comp_id = user.company_id or "C001"

        token = create_access_token({"sub": user.id})
        headers = {"Authorization": f"Bearer {token}"}

        # 1. GET data
        resp_data = client.get(f"/api/companies/{comp_id}/tax-declaration/data?year=2025", headers=headers)
        assert resp_data.status_code == 200
        json_data = resp_data.json()
        assert "inn" in json_data
        assert json_data["year"] == 2025
        assert "tax_q1" in json_data

        # 2. POST generate PDF
        resp_pdf = client.post(
            f"/api/companies/{comp_id}/tax-declaration/generate-pdf",
            headers=headers,
            json=json_data
        )
        assert resp_pdf.status_code == 200
        assert resp_pdf.headers["content-type"] == "application/pdf"
        assert len(resp_pdf.content) > 5000
        assert resp_pdf.content.startswith(b"%PDF-")
    finally:
        db.close()
