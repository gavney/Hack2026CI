# -*- coding: utf-8 -*-
"""
Risk evaluation and AI-powered Cash Gap Breakdown with GigaChat.
"""
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import uuid
import sys
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger("CashGapAI")

_gigachat_client = None

def get_gigachat_client():
    global _gigachat_client
    if _gigachat_client is not None:
        return _gigachat_client
    try:
        root_dir = Path(__file__).resolve().parent.parent.parent
        ml_dir = root_dir / "ML"
        if str(ml_dir) not in sys.path:
            sys.path.insert(0, str(ml_dir))
        from gigachat import GigaChatClient
        _gigachat_client = GigaChatClient()
        return _gigachat_client
    except Exception as e:
        logger.warning(f"Could not initialize GigaChatClient: {e}")
        return None


def evaluate_cash_gap(
    forecast_result: Dict[str, Any],
    mandatory_slots: List[Dict[str, Any]],
    overdraft_limit: float = 0.0,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    as_of: Optional[date] = None,
    gigachat_enabled: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Evaluates cash gap risk and generates AI breakdown via GigaChat:
    - Critical liquidity deficit (peak deficit calculated strictly from the forecast graph).
    - Drawdown duration (if deficit does not recover by end of horizon, explicitly notes 'Не выходит из дефицита до конца горизонта').
    - Slice of cash flows from current day (as_of) through gap date and horizon passed to GigaChat.
    - GigaChat system prompt generates main_factor, reason, and 3 concrete prevention steps.
    """
    days = forecast_result.get("days", [])
    if not days:
        return None

    effective_threshold = -float(overdraft_limit or 0.0)

    # 1. Evaluate deficit days on median (p50) and stress (p10)
    deficit_days_p50 = [i for i, d in enumerate(days) if d.get("p50", 0.0) < effective_threshold]
    deficit_days_p10 = [i for i, d in enumerate(days) if d.get("p10", 0.0) < effective_threshold]

    # Calculate mandatory 7-day payment buffer for soft gap
    mandatory_7d = sum(s.get("typical_amount", 0.0) for s in mandatory_slots) * 0.25
    soft_gap_days = [i for i, d in enumerate(days[:14]) if d.get("p50", 0.0) < mandatory_7d]

    has_hard_gap = len(deficit_days_p50) > 0 or len(deficit_days_p10) > 0
    has_soft_gap = len(soft_gap_days) > 0 and not has_hard_gap
    first_gap_date = forecast_result.get("first_gap_date")
    max_prob = float(forecast_result.get("gap_probability", 0.0) or 0.0)

    if not has_hard_gap and not has_soft_gap and not first_gap_date and max_prob < 0.20:
        return None

    # Determine first gap date and start index
    if deficit_days_p50:
        start_idx = deficit_days_p50[0]
        first_gap_date = days[start_idx]["date"]
        track_metric = "p50"
    elif deficit_days_p10:
        start_idx = deficit_days_p10[0]
        first_gap_date = days[start_idx]["date"]
        track_metric = "p10"
    elif soft_gap_days:
        start_idx = soft_gap_days[0]
        first_gap_date = days[start_idx]["date"]
        track_metric = "soft"
    else:
        start_idx = 0
        track_metric = "p10"

    # 2. Critical Liquidity Deficit (Критический дефицит ликвидности по графику)
    peak_shortfall_p50 = max([abs(effective_threshold - d["p50"]) for d in days if d.get("p50", 0.0) < effective_threshold] or [0.0])
    peak_shortfall_p10 = max([abs(effective_threshold - d["p10"]) for d in days if d.get("p10", 0.0) < effective_threshold] or [0.0])

    if peak_shortfall_p50 > 0:
        critical_deficit = peak_shortfall_p50
    elif peak_shortfall_p10 > 0:
        critical_deficit = peak_shortfall_p10
    elif has_soft_gap:
        critical_deficit = max(mandatory_7d - days[start_idx].get("p10", 0.0), 50000.0)
    else:
        critical_deficit = float(forecast_result.get("total_shortfall_p10", 0.0) or 50000.0)

    critical_deficit = round(float(critical_deficit), 2)
    shortfall_p10 = round(float(peak_shortfall_p10 if peak_shortfall_p10 > 0 else critical_deficit * 1.25), 2)
    shortfall_p50 = round(float(peak_shortfall_p50 if peak_shortfall_p50 > 0 else critical_deficit), 2)

    # 3. Drawdown Duration (Длительность просадки)
    # Если не выходит из дефицита до конца горизонта — явно указываем это
    recovers = False
    recovery_idx = None
    if track_metric in ["p50", "p10"]:
        metric_key = "p50" if track_metric == "p50" else "p10"
        for j in range(start_idx + 1, len(days)):
            if days[j].get(metric_key, 0.0) >= effective_threshold:
                recovers = True
                recovery_idx = j
                break
    elif track_metric == "soft":
        for j in range(start_idx + 1, len(days)):
            if days[j].get("p50", 0.0) >= mandatory_7d:
                recovers = True
                recovery_idx = j
                break

    start_date_val = days[start_idx]["date"]
    start_date_str = start_date_val.strftime("%d.%m.%Y") if hasattr(start_date_val, "strftime") else str(start_date_val)

    if recovers and recovery_idx is not None:
        duration_days = recovery_idx - start_idx
        end_date_val = days[recovery_idx]["date"]
        end_date_str = end_date_val.strftime("%d.%m.%Y") if hasattr(end_date_val, "strftime") else str(end_date_val)
        duration_text = f"{duration_days} дн. (с {start_date_str} по {end_date_str})"
    else:
        duration_days = len(days) - start_idx
        duration_text = f"Не выходит из дефицита до конца горизонта ({duration_days} дн., с {start_date_str})"

    # 4. Pure Algorithmic Evaluation (Fast, 0ms, used for Radar tab)
    reason = (
        f"Деньги могут закончиться {start_date_str}. "
        f"Ожидаемый дефицит: от {shortfall_p50:,.0f} ₽ до {shortfall_p10:,.0f} ₽ в пике "
        f"(в неблагоприятном сценарии до {shortfall_p10:,.0f} ₽). "
        f"Вероятность разрыва {int(round(max_prob * 100))}%."
    )

    main_factor = "Налоговое списание ЕНП и кассовое смещение" if has_soft_gap else "Снижение поступлений при плановых расходах"

    needed = max(critical_deficit, 100000.0)
    actions = [
        {
            "id": "act_prepay",
            "title": "Запросить досрочную оплату у покупателей",
            "description": "Свяжитесь с ключевыми дебиторами и предложите скидку 2% за оплату в течение 3 дней.",
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
            "id": "act_cost_cut",
            "title": "Временно заморозить некритичные расходы",
            "description": "Приостановите закупку инвентаря, рекламу и прочие несущественные расходы до нормализации ликвидности.",
            "estimated_effect": round(needed * 0.35, 2),
            "action_type": "cost_reduction"
        }
    ]

    level = "critical" if (max_prob >= 0.50 or critical_deficit >= 150000.0) else "warning"

    return {
        "id": f"alt_{uuid.uuid4().hex[:8]}",
        "level": level,
        "gap_date": first_gap_date,
        "gap_amount": critical_deficit,
        "shortfall_p10": shortfall_p10,
        "shortfall_p50": shortfall_p50,
        "duration_days": duration_days,
        "duration_text": duration_text,
        "main_factor": main_factor,
        "probability": round(max_prob, 2),
        "reason": reason,
        "ai_reason": None,
        "actions": actions,
        "acknowledged": False
    }


def generate_gigachat_breakdown(
    forecast_result: Dict[str, Any],
    mandatory_slots: Optional[List[Dict[str, Any]]] = None,
    overdraft_limit: float = 0.0,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    as_of: Optional[date] = None
) -> Dict[str, Any]:
    """
    Dedicated AI-powered Cash Gap Breakdown with GigaChat for the 'Разбор' tab.
    Constructs timeline excerpt from current day through gap date and horizon,
    queries GigaChat with system prompt, and returns main_factor, economic reason,
    and 3 actionable steps with simulated financial effects.
    """
    days = forecast_result.get("days", [])
    if not days:
        return {
            "main_factor": "Нет данных прогноза",
            "ai_reason": "Недостаточно данных для анализа кассового разрыва.",
            "actions": [],
            "gap_amount": 0.0,
            "duration_text": "—"
        }

    # Evaluate algorithmic base first to get accurate metrics
    base_eval = evaluate_cash_gap(
        forecast_result=forecast_result,
        mandatory_slots=mandatory_slots or [],
        overdraft_limit=overdraft_limit,
        company_name=company_name,
        industry=industry,
        events=events,
        as_of=as_of
    )

    if not base_eval:
        return {
            "main_factor": "Кассовый разрыв не обнаружен",
            "ai_reason": "Денежных средств достаточно для выполнения всех плановых обязательств бизнеса.",
            "actions": [],
            "gap_amount": 0.0,
            "duration_text": "Дефицит отсутствует"
        }

    critical_deficit = base_eval["gap_amount"]
    duration_text = base_eval["duration_text"]
    first_gap_date = base_eval["gap_date"]
    start_date_str = first_gap_date.strftime("%d.%m.%Y") if hasattr(first_gap_date, "strftime") else str(first_gap_date)

    # Prepare timeline excerpt (from current day through gap date to end of window)
    contribs_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for c in (forecast_result.get("contributions") or []):
        dt_key = str(c.get("date"))
        contribs_by_date.setdefault(dt_key, []).append(c)

    timeline_excerpt = []
    for i, d in enumerate(days):
        d_val = d["date"]
        d_str = d_val.strftime("%Y-%m-%d") if hasattr(d_val, "strftime") else str(d_val)
        bal_p50 = d.get("p50", 0.0)
        bal_p10 = d.get("p10", 0.0)
        prob_neg = d.get("prob_negative", 0.0)

        day_events = contribs_by_date.get(d_str, [])
        events_desc = []
        for ev in day_events:
            amt = ev.get("amount", 0.0)
            sign = "+" if amt > 0 else ""
            cat = ev.get("category_id") or "платеж"
            cp = ev.get("counterparty_name") or ev.get("note") or ""
            events_desc.append(f"{cat} {sign}{amt:,.0f} ₽ ({cp})".strip())

        marker = ""
        if str(d_val) == str(first_gap_date):
            marker = " [ДЕНЬ ПЕРВОГО РАЗРЫВА]"

        ev_str = "; ".join(events_desc) if events_desc else "плановые операции"
        timeline_excerpt.append(
            f"День {i+1} ({d_str}){marker}: P50 = {bal_p50:,.0f} ₽, P10 = {bal_p10:,.0f} ₽, риск = {prob_neg*100:.0f}%. События: {ev_str}"
        )

    system_prompt = (
        "Ты — ведущий финансовый риск-аналитик.\n"
        "Твоя задача — детально проанализировать выдержку ежедневных денежных потоков клиента с текущего дня через день кассового разрыва и далее до конца прогнозного окна, "
        "выявить точную экономическую причину разрыва и предложить ровно 3 конкретных, практически реализуемых управленческих шага для предотвращения дефицита.\n\n"
        "ВАЖНО: В программе НЕТ овердрафта и кредитов! Категорически ЗАПРЕЩЕНО предлагать овердрафт или кредитные линии. Все 3 шага должны быть реальными операционными решениями самого бизнеса:\n"
        "1. Перенос / отсрочка платежа поставщику (delay_payment)\n"
        "2. Ускорение поступления от покупателей со скидкой 2-3% или факторинг дебиторки (request_prepayment)\n"
        "3. Временная оптимизация / заморозка некритичных расходов бизнеса (cost_reduction)\n\n"
        "Требования к ответу:\n"
        "1. Формат — строго валидный JSON без markdown-разметки (без ```json).\n"
        "2. Структура JSON:\n"
        "{\n"
        '  "main_factor": "Краткая суть причины дефицита (3-7 слов, например: \'Налоговый платеж ЕНП при задержке дебиторки\')",\n'
        '  "reason": "Подробное, экспертное объяснение для руководителя бизнеса (2-4 предложения): почему возник дефицит, в какую дату, какие конкретно списания и задержки поступлений его спровоцировали, и каков масштаб просадки.",\n'
        '  "actions": [\n'
        "    {\n"
        '      "id": "act_delay",\n'
        '      "title": "Первый конкретный шаг (например: Согласовать отсрочку платежа поставщику ООО ...)",\n'
        '      "description": "Что именно сделать: кому позвонить, на какой срок отложить платеж, как аргументировать",\n'
        '      "estimated_effect": 300000.0,\n'
        '      "action_type": "delay_payment"\n'
        "    },\n"
        "    {\n"
        '      "id": "act_prepay",\n'
        '      "title": "Второй конкретный шаг (например: Запросить досрочную оплату дебиторской задолженности со скидкой 2%)",\n'
        '      "description": "Что именно сделать: связаться с покупателем, предложить скидку за расчет в течение 3 дней",\n'
        '      "estimated_effect": 250000.0,\n'
        '      "action_type": "request_prepayment"\n'
        "    },\n"
        "    {\n"
        '      "id": "act_cost_cut",\n'
        '      "title": "Третий конкретный шаг (например: Временно заморозить закупку инвентаря и рекламу)",\n'
        '      "description": "Приостановить необязательные текущие выплаты до нормализации кассового остатка",\n'
        '      "estimated_effect": 200000.0,\n'
        '      "action_type": "cost_reduction"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_message = (
        f"Компания: {company_name or 'Бизнес-клиент'}, отрасль: {industry or 'Торговля и услуги'}\n"
        f"Лимит овердрафта в банке: {overdraft_limit:,.0f} ₽\n"
        f"Дата возникновения дефицита: {start_date_str}\n"
        f"Критический дефицит ликвидности по графику: {critical_deficit:,.0f} ₽\n"
        f"Длительность просадки: {duration_text}\n\n"
        "Выдержка ежедневных денежных потоков и прогноза (с текущего дня по конец горизонта):\n"
        + "\n".join(timeline_excerpt)
    )

    main_factor = None
    ai_reason = None
    actions = None

    gc = get_gigachat_client()
    if gc:
        try:
            res = gc.chat_with_system_message(
                system_message=system_prompt,
                user_message=user_message,
                model="GigaChat"
            )
            if res and "choices" in res and res["choices"]:
                content = res["choices"][0]["message"]["content"]
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned.rsplit("\n", 1)[0]
                cleaned = cleaned.strip()
                parsed = json.loads(cleaned)
                main_factor = parsed.get("main_factor")
                ai_reason = parsed.get("reason")
                raw_actions = parsed.get("actions")
                if raw_actions and isinstance(raw_actions, list) and len(raw_actions) >= 3:
                    actions = []
                    for idx, act in enumerate(raw_actions[:3]):
                        actions.append({
                            "id": act.get("id") or f"act_ai_{idx+1}",
                            "title": act.get("title", f"Действие {idx+1}"),
                            "description": act.get("description", ""),
                            "estimated_effect": float(act.get("estimated_effect") or (critical_deficit * 0.5)),
                            "action_type": act.get("action_type") or ("delay_payment" if idx == 0 else "request_prepayment" if idx == 1 else "cost_reduction")
                        })
        except Exception as e:
            logger.warning(f"GigaChat analysis error, applying fallback: {e}")

    # Fallbacks if GigaChat failed or timed out
    if not main_factor:
        main_factor = base_eval["main_factor"]

    if not ai_reason:
        ai_reason = (
            f"Просадка ликвидности компании {company_name or ''} начинается с {start_date_str}. "
            f"Основной фактор — превышение регулярных обязательств над поступающими платежами. "
            f"Прогнозируемый критический дефицит составляет {critical_deficit:,.0f} ₽. Длительность: {duration_text}."
        )

    if not actions:
        actions = base_eval["actions"]

    return {
        "main_factor": main_factor,
        "ai_reason": ai_reason,
        "actions": actions,
        "gap_amount": critical_deficit,
        "duration_text": duration_text,
        "gap_date": first_gap_date
    }
