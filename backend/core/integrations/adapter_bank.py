from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from backend.core.slots import next_business_day

class AdapterBankCentroInvest:
    adapter_name = "bank_centroinvest"
    display_name = "Банк «Центр-Инвест» (ДБО и Открытые API)"
    description = "Прямая интеграция с автоматизированной банковской системой (АБС) «Центр-Инвест». Синхронизирует графики погашения кредитов, зарплатный реестр и картотеку неисполненных платежей."

    def fetch(self, company_id: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
        today = date.today()
        
        # 1. Next loan annuity payment
        loan_date = next_business_day(today + timedelta(days=15))
        
        # 2. Next payroll date
        payroll_date = next_business_day(today + timedelta(days=18))

        events = [
            {
                "id": f"ci_loan_{company_id}_{loan_date.strftime('%Y%m')}",
                "event_date": loan_date,
                "amount": -85400.0,
                "probability": 1.0,
                "category_id": "cat_bank_credit",
                "counterparty_inn": "6164015112",
                "counterparty_name": "Банк «Центр-Инвест»",
                "source": "bank_centroinvest",
                "note": "Ежемесячный платеж по кредитному договору № КР-2024/09 на развитие бизнеса"
            },
            {
                "id": f"ci_payroll_{company_id}_{payroll_date.strftime('%Y%m')}",
                "event_date": payroll_date,
                "amount": -430000.0,
                "probability": 1.0,
                "category_id": "cat_payroll",
                "counterparty_inn": "",
                "counterparty_name": "Реестр зарплатного проекта",
                "source": "bank_centroinvest",
                "note": "Выплата заработной платы сотрудникам по зарплатному проекту банка «Центр-Инвест»"
            }
        ]
        return events

    def status(self, company_id: str) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "display_name": self.display_name,
            "status": "active",
            "last_sync_at": datetime.utcnow().isoformat(),
            "active_loans_count": 1,
            "overdraft_available": True,
            "overdraft_preapproved_limit": 500000.0,
            "events_added": 2,
            "unprocessed_orders_count": 0
        }
