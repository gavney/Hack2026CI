from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import uuid

def evaluate_cash_gap(
    forecast_result: Dict[str, Any],
    mandatory_slots: List[Dict[str, Any]],
    overdraft_limit: float = 0.0
) -> Optional[Dict[str, Any]]:
    """
    Evaluates cash gap risk according to section 3.6 (FR-6.1 - FR-6.5):
    - Hard gap: balance < -overdraft_limit
    - Soft gap: balance < upcoming 7-day mandatory payments
    - Calculates probability, gap date, shortfall at p10 and p50
    - Generates human-friendly explanation and 3 concrete recommendations
    """
    days = forecast_result.get("days", [])
    if not days:
        return None

    first_gap_date = forecast_result.get("first_gap_date")
    max_prob = forecast_result.get("gap_probability", 0.0)
    shortfall_p10 = forecast_result.get("total_shortfall_p10", 0.0)

    # Calculate 7-day mandatory buffer
    mandatory_7d = sum(s.get("typical_amount", 0.0) for s in mandatory_slots) * 0.25

    # Check for soft gap if hard gap is not triggered
    is_soft_gap = False
    if not first_gap_date:
        for d in days[:14]:
            if d["p50"] < mandatory_7d:
                first_gap_date = d["date"]
                shortfall_p10 = mandatory_7d - d["p10"]
                max_prob = max(0.25, d["prob_negative"])
                is_soft_gap = True
                break

    if not first_gap_date and max_prob < 0.20:
        return None

    # Determine alert level
    if max_prob >= 0.50:
        level = "critical"
    elif max_prob >= 0.20:
        level = "warning"
    else:
        level = "info"

    gap_date_str = first_gap_date.strftime("%d.%m.%Y") if isinstance(first_gap_date, (date,)) else str(first_gap_date)
    prob_percent = int(round(max_prob * 100))

    # Calculate shortfall at median
    shortfall_p50 = 0.0
    for d in days:
        if d["date"] == first_gap_date:
            if d["p50"] < -overdraft_limit:
                shortfall_p50 = abs(d["p50"] - (-overdraft_limit))
            break

    max_shortfall_p50 = max([abs(d["p50"] - (-overdraft_limit)) for d in days if d["p50"] < -overdraft_limit] or [0.0])
    shortfall_p50 = round(shortfall_p50, 2)
    shortfall_p10 = round(shortfall_p10, 2)
    if shortfall_p10 <= 0:
        shortfall_p10 = max(50000.0, shortfall_p50 * 1.3)

    # Explanation template matching section 4.4
    if is_soft_gap:
        if shortfall_p50 > 0:
            deficit_text = f"Ожидаемый дефицит: ~{shortfall_p50:,.0f} ₽ (в неблагоприятном случае до {shortfall_p10:,.0f} ₽)"
        else:
            deficit_text = f"В неблагоприятном случае нехватка составит до {shortfall_p10:,.0f} ₽"
        reason = (
            f"Внимание: к {gap_date_str} остаток на счёте опустится ниже суммы обязательных платежей на неделю. "
            f"{deficit_text}. Вероятность кассового напряжения {prob_percent}%."
        )
    else:
        if shortfall_p50 > 0:
            if max_shortfall_p50 > shortfall_p50:
                deficit_text = f"Ожидаемый дефицит: от {shortfall_p50:,.0f} ₽ до {max_shortfall_p50:,.0f} ₽ в пике"
            else:
                deficit_text = f"Ожидаемый дефицит: ~{shortfall_p50:,.0f} ₽"
            if shortfall_p10 > max(shortfall_p50, max_shortfall_p50):
                deficit_text += f" (в неблагоприятном сценарии до {shortfall_p10:,.0f} ₽)"
        else:
            deficit_text = f"При неблагоприятном сценарии нехватка средств составит до {shortfall_p10:,.0f} ₽"

        reason = (
            f"Деньги могут закончиться {gap_date_str}. "
            f"{deficit_text}. Вероятность разрыва {prob_percent}%."
        )

    # 3 Action Recommendations (FR-6.5)
    needed = max(shortfall_p10, shortfall_p50, 100000.0)
    actions = [
        {
            "id": "act_prepay",
            "title": "Запросить досрочную оплату у клиентов",
            "description": "Свяжитесь с ключевыми контрагентами и предложите скидку 2% за оплату в течение 3 дней.",
            "estimated_effect": round(needed * 0.6, 2),
            "action_type": "request_prepayment"
        },
        {
            "id": "act_delay_supplier",
            "title": "Согласовать отсрочку платежа поставщику",
            "description": "Перенесите списание за закупку товаров или сырья на 7–10 дней без штрафных санкций.",
            "estimated_effect": round(needed * 0.45, 2),
            "action_type": "delay_payment"
        },
        {
            "id": "act_credit_ci",
            "title": "Краткосрочное финансирование кассового разрыва",
            "description": "Экспресс-финансирование оборотных средств от банка «Центр-Инвест» для закрытия кассового дефицита.",
            "estimated_effect": round(needed, 2),
            "action_type": "request_credit"
        }
    ]

    return {
        "id": f"alt_{uuid.uuid4().hex[:8]}",
        "level": level,
        "gap_date": first_gap_date,
        "shortfall_p10": shortfall_p10,
        "shortfall_p50": shortfall_p50,
        "probability": round(max_prob, 2),
        "reason": reason,
        "actions": actions,
        "acknowledged": False
    }
