from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

class AdapterEDO:
    adapter_name = "edo_diadoc"
    display_name = "ЭДО Диадок / СБИС"
    description = "Интеграция с операторами юридически значимого электронного документооборота. Загружает подписанные акты, договоры и накладные с условиями отсрочки."

    def fetch(self, company_id: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
        today = date.today()
        return [
            {
                "id": f"edo_act_{company_id}_1",
                "event_date": today + timedelta(days=9),
                "amount": 210000.0,
                "probability": 0.88,
                "category_id": "cat_revenue_client",
                "counterparty_inn": "6163098124",
                "counterparty_name": "ООО «Ростов-Трейд»",
                "source": "edo_diadoc",
                "note": "Подписанный акт приема-передачи работ № 88 через Диадок. Отсрочка 10 дней."
            }
        ]

    def status(self, company_id: str) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "display_name": self.display_name,
            "status": "active",
            "last_sync_at": datetime.utcnow().isoformat(),
            "operator": "Контур.Диадок",
            "events_added": 1
        }

class AdapterMarketplaces:
    adapter_name = "marketplaces"
    display_name = "Маркетплейсы (WB / Ozon)"
    description = "Интеграция с личными кабинетами селлера Wildberries и Ozon. Прогнозирует еженедельные выплаты выручки за вычетом комиссий."

    def fetch(self, company_id: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
        today = date.today()
        return [
            {
                "id": f"mp_wb_{company_id}_1",
                "event_date": today + timedelta(days=4),
                "amount": 165000.0,
                "probability": 0.98,
                "category_id": "cat_revenue_client",
                "counterparty_inn": "7721546864",
                "counterparty_name": "ООО «Вайлдберриз»",
                "source": "marketplaces",
                "note": "Еженедельный отчет реализации маркетплейса Wildberries к перечислению"
            }
        ]

    def status(self, company_id: str) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "display_name": self.display_name,
            "status": "active",
            "last_sync_at": datetime.utcnow().isoformat(),
            "connected_platforms": ["Wildberries", "Ozon"],
            "events_added": 1
        }
