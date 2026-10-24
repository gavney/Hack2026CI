import re
import math
import hashlib
from typing import Dict, Any, Optional, Tuple, List

# Standard predefined categories with roles, colors and icons
STANDARD_CATEGORIES = [
    # Inflows
    {
        "id": "cat_revenue_client",
        "name": "Выручка от клиентов",
        "cashflow_role": "variable_in",
        "color": "#16a34a",
        "icon": "banknote"
    },
    {
        "id": "cat_revenue_acquiring",
        "name": "Эквайринг и СБП",
        "cashflow_role": "variable_in",
        "color": "#15803d",
        "icon": "credit-card"
    },
    {
        "id": "cat_owner_deposit",
        "name": "Деньги от владельца",
        "cashflow_role": "one_off",
        "color": "#059669",
        "icon": "user-plus"
    },
    {
        "id": "cat_refund_in",
        "name": "Возвраты от поставщиков",
        "cashflow_role": "refund",
        "color": "#0d9488",
        "icon": "rotate-ccw"
    },
    {
        "id": "cat_other_in",
        "name": "Прочие поступления",
        "cashflow_role": "variable_in",
        "color": "#0284c7",
        "icon": "arrow-down-left"
    },

    # Outflows - Regular
    {
        "id": "cat_payroll",
        "name": "Люди (зарплата и аванс)",
        "cashflow_role": "regular_out",
        "color": "#2563eb",
        "icon": "users"
    },
    {
        "id": "cat_rent_utilities",
        "name": "Аренда и коммуналка",
        "cashflow_role": "regular_out",
        "color": "#7c3aed",
        "icon": "building"
    },
    {
        "id": "cat_tax_enp",
        "name": "Налоги и взносы (ЕНП)",
        "cashflow_role": "tax",
        "color": "#dc2626",
        "icon": "receipt"
    },
    {
        "id": "cat_bank_credit",
        "name": "Банк и кредиты",
        "cashflow_role": "regular_out",
        "color": "#475569",
        "icon": "landmark"
    },

    # Outflows - Variable
    {
        "id": "cat_procurement",
        "name": "Закупки и сырьё",
        "cashflow_role": "variable_out",
        "color": "#ea580c",
        "icon": "shopping-bag"
    },
    {
        "id": "cat_transport",
        "name": "Транспорт и авто",
        "cashflow_role": "variable_out",
        "color": "#d97706",
        "icon": "truck"
    },
    {
        "id": "cat_services_marketing",
        "name": "Маркетинг и сервисы",
        "cashflow_role": "variable_out",
        "color": "#9333ea",
        "icon": "megaphone"
    },
    {
        "id": "cat_owner_draw",
        "name": "Деньги владельцу",
        "cashflow_role": "one_off",
        "color": "#0891b2",
        "icon": "wallet"
    },
    {
        "id": "cat_refund_out",
        "name": "Возвраты покупателям",
        "cashflow_role": "refund",
        "color": "#b91c1c",
        "icon": "undo"
    },
    {
        "id": "cat_other_out",
        "name": "Прочие расходы",
        "cashflow_role": "variable_out",
        "color": "#64748b",
        "icon": "help-circle"
    },

    # Not income and not expense
    {
        "id": "cat_transfer_own",
        "name": "Перевод между своими счетами",
        "cashflow_role": "transfer_own",
        "color": "#94a3b8",
        "icon": "repeat"
    }
]

CATEGORY_LOOKUP = {c["id"]: c for c in STANDARD_CATEGORIES}

def normalize_purpose(text: Any) -> str:
    """Normalizes payment purpose string"""
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return ""
    text = str(text)
    if not text.strip():
        return ""
    text = text.lower().replace("ё", "е")
    # Replace dates like 12.05.2025 with #
    text = re.sub(r'\b\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b', '#', text)
    # Replace numbers, account numbers, amounts with #
    text = re.sub(r'\b\d+([.,]\d+)?\b', '#', text)
    text = re.sub(r'["«»„“”\(\)\[\]\':;*]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Fixed priority regex rules for categorization (FR-2.3)
RULES = [
    # 1. Taxes (FR-3.2.2 Normalization of ENP / Taxes)
    {
        "category_id": "cat_tax_enp",
        "direction": "Списание",
        "pattern": re.compile(r'(единый\s+налогов(ый|ого)\s+платеж|енп|налог\s+на\s+доход|страхов(ые|ых)\s+взнос|ндфл|уплату\s+налога|фнс\s+россии|госпошлин|в\s+бюджет|пени\s+по\s+налог)', re.IGNORECASE),
        "confidence": 0.99
    },
    # 2. Own account transfer (transfer_own)
    {
        "category_id": "cat_transfer_own",
        "direction": None,
        "pattern": re.compile(r'(перевод\s+собственн(ых|ого)\s+средств|между\s+своими\s+счетами|перевод\s+на\s+свой\s+счет|перевод\s+со\s+своего\s+счета)', re.IGNORECASE),
        "confidence": 0.98
    },
    # 3. Owner draw / deposit
    {
        "category_id": "cat_owner_draw",
        "direction": "Списание",
        "pattern": re.compile(r'(на\s+личные\s+нужды|доход\s+индивидуального\s+предпринимателя|перевод\s+дохода|выплата\s+дивидендов|снятие\s+по\s+бизнес-карте|перевод\s+средств\s+физическому\s+лицу)', re.IGNORECASE),
        "confidence": 0.95
    },
    {
        "category_id": "cat_owner_deposit",
        "direction": "Поступление",
        "pattern": re.compile(r'(взнос\s+в\s+уставный|заем\s+учредител|пополнение\s+собственными|финансовая\s+помощь\s+учредител)', re.IGNORECASE),
        "confidence": 0.95
    },
    # 4. Payroll (Люди: зарплата, аванс, премия, ГПХ)
    {
        "category_id": "cat_payroll",
        "direction": "Списание",
        "pattern": re.compile(r'(заработная\s+плата|зарплат|аванс\s+за|расчет\s+при\s+увольнен|по\s+реестру\s+№|выплата\s+по\s+договору\s+гпх|оплата\s+труда|преми[яи]|компенсация\s+отпуск)', re.IGNORECASE),
        "confidence": 0.98
    },
    # 5. Rent & utilities (Аренда и коммуналка)
    {
        "category_id": "cat_rent_utilities",
        "direction": "Списание",
        "pattern": re.compile(r'(аренд(а|ная|ной|у)\s+(помещен|офис|склад|авто)|субаренд|электроэнерг|водоснабжен|отоплен|коммунальн(ые|ых)\s+услуг|за\s+аренду|эксплуатационные\s+расходы)', re.IGNORECASE),
        "confidence": 0.96
    },
    # 6. Banking & credits (Кредиты, лизинг, комиссии)
    {
        "category_id": "cat_bank_credit",
        "direction": "Списание",
        "pattern": re.compile(r'(комисси(я|и)|обслуживание\s+счет|процент(ы|ов)\s+по\s+кредит|погашение\s+кредит|основного\s+долга\s+по\s+договору|лизинг|овердрафт|плата\s+за\s+ведение\s+счета|пао\s+«банк»|банк\s+«центр-инвест»)', re.IGNORECASE),
        "confidence": 0.95
    },
    # 7. Refunds (Rule "возврат" only applied at the beginning of purpose as per FR-2.3)
    {
        "category_id": "cat_refund_out",
        "direction": "Списание",
        "pattern": re.compile(r'^(возврат\s+денежных|возврат\s+ошибочно|возврат\s+покупателю|возврат\s+средств|возврат\s+переплаты)', re.IGNORECASE),
        "confidence": 0.95
    },
    {
        "category_id": "cat_refund_in",
        "direction": "Поступление",
        "pattern": re.compile(r'^(возврат\s+от\s+поставщика|возврат\s+излишне\s+уплачен|возврат\s+обеспечительного)', re.IGNORECASE),
        "confidence": 0.95
    },
    # 8. Inflow: Client acquiring / SBP
    {
        "category_id": "cat_revenue_acquiring",
        "direction": "Поступление",
        "pattern": re.compile(r'(эквайринг|сбп|быстрых\s+платежей|по\s+операциям\s+с\s+банковскими\s+картами|возмещени(е|я)\s+по\s+эквайринг|терминал|qr-код|система\s+быстрых)', re.IGNORECASE),
        "confidence": 0.98
    },
    # 9. Outflow: Transport, auto repair, fuel, Platon
    {
        "category_id": "cat_transport",
        "direction": "Списание",
        "pattern": re.compile(r'(гсм|топлив|бензин|дизель|газпромнефть|лукойл|роснефть|грузоперевозк|транспортн(ые|ых)\s+услуг|доставк|система\s+взимания\s+платы|провоз(а)?\s+по\s+дорогам|автосервис|ремонт\s+авто|шин(ы|омонтаж)|запчаст|техобслуживан)', re.IGNORECASE),
        "confidence": 0.94
    },
    # 10. Outflow: Services & Marketing (Cleaning, IT, ads, legal, consulting)
    {
        "category_id": "cat_services_marketing",
        "direction": "Списание",
        "pattern": re.compile(r'(реклам|яндекс|yandex|вконтакте|vk\s+ads|интернет|связь|бухгалтерск|юридическ|хостинг|программн(ого|ое)|подписка|лицензи|клининг|услуги\s+уборки|аудит|консультац|охрана|канцтовар|учетные\s+системы)', re.IGNORECASE),
        "confidence": 0.93
    },
    # 11. Outflow: Supplier procurement (Goods, raw materials, wholesale, construction)
    {
        "category_id": "cat_procurement",
        "direction": "Списание",
        "pattern": re.compile(r'(за\s+поставк|по\s+накладной|товар|сырь|материал|закупк|поставщик|продукц|оборудован|упд|счету\s+№|за\s+мебель|за\s+продукты|за\s+металл)', re.IGNORECASE),
        "confidence": 0.91
    },
    # 12. Inflow: Customer payment by invoice/contract/UPD/services/freight
    {
        "category_id": "cat_revenue_client",
        "direction": "Поступление",
        "pattern": re.compile(r'(оплат(а|у)|по\s+счет|по\s+договор|упд|перевозк|экспедиционн|за\s+оказан(ие|ные)\s+услуг|за\s+товар|за\s+выполненные\s+работ|предоплат|выручка|покупател|доплат|частичн(ая)?\s+оплат)', re.IGNORECASE),
        "confidence": 0.92
    }
]

def classify_operation(
    direction: str,
    payment_purpose: str,
    counterparty_inn: str,
    counterparty_name: str = "",
    memory_dict: Optional[Dict[str, str]] = None
) -> Tuple[str, float, str]:
    """
    Classifies operation according to cascade (FR-2.2):
    1. User memory lookup by normalized key (FR-2.4)
    2. Fixed priority regex rules (FR-2.3)
    3. Fallback to general category with lower confidence
    
    Returns: (category_id, confidence, source)
    """
    norm_p = normalize_purpose(payment_purpose)
    norm_key = f"{norm_p}||{counterparty_inn or ''}"

    # 1. User memory check
    if memory_dict and norm_key in memory_dict:
        return memory_dict[norm_key], 1.0, "memory"

    # 2. Rule matching
    search_text = f"{norm_p} {counterparty_name.lower().replace('ё', 'е')}"
    for rule in RULES:
        if rule["direction"] is None or rule["direction"] == direction:
            if rule["pattern"].search(search_text):
                return rule["category_id"], rule["confidence"], "rule"

    # 3. Fallback
    if direction == "Поступление":
        return "cat_other_in", 0.50, "rule_fallback"
    else:
        return "cat_other_out", 0.50, "rule_fallback"

def anonymize_for_llm(payment_purpose: str) -> str:
    """Anonymizes purpose text for external LLM according to FR-2.7 (no INNs, no names, no exact numbers)"""
    return normalize_purpose(payment_purpose)
