from backend.core.categorizer import classify_operation, normalize_purpose

def test_tax_enp_normalization():
    # Various tax phrases must all map to cat_tax_enp
    variants = [
        "Единый налоговый платеж за 2 квартал 2025",
        "ЕНП без НДС",
        "Единый налоговый платёж. НДС не облагается",
        "Уплата налога в бюджет по требованию ФНС России"
    ]
    for text in variants:
        cat_id, conf, src = classify_operation("Списание", text, "7707329152")
        assert cat_id == "cat_tax_enp", f"Failed on '{text}' -> got {cat_id}"

def test_user_memory_precedence():
    memory = {"специальный платеж за консультацию||7701234567": "cat_services_marketing"}
    cat_id, conf, src = classify_operation(
        direction="Списание",
        payment_purpose="Специальный платеж за консультацию",
        counterparty_inn="7701234567",
        memory_dict=memory
    )
    assert cat_id == "cat_services_marketing"
    assert src == "memory"
    assert conf == 1.0

def test_refund_rule_only_at_beginning():
    # At start -> refund
    cat_start, _, _ = classify_operation("Списание", "Возврат ошибочно перечисленных средств по письму", "1234567890")
    assert cat_start == "cat_refund_out"

    # In the middle (not refund, e.g. purchasing goods with word return inside description)
    cat_middle, _, _ = classify_operation("Списание", "Оплата по счету № 12 за товар без возможности возвратов", "1234567890")
    assert cat_middle != "cat_refund_out"
