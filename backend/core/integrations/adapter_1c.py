from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import uuid

class Adapter1CEnterprise:
    adapter_name = "1c_enterprise"
    display_name = "1С:Предприятие 8.3 (Счета и Договоры)"
    description = "Интеграция через протокол 1C:OData и обмен 1CClientBankExchange. Загружает выставленные счета клиентам и входящие счета поставщиков."

    def fetch(self, company_id: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Simulates 1C:Enterprise sync:
        Pulls issued invoices to buyers and supplier invoices.
        """
        today = date.today()
        
        # Synthetic realistic 1C document fixtures
        mock_invoices = [
            {
                "id": f"1c_inv_{company_id}_101",
                "event_date": today + timedelta(days=5),
                "amount": 345000.0,  # Buyer invoice (inflow)
                "probability": 0.90,
                "category_id": "cat_revenue_client",
                "counterparty_inn": "6164289012",
                "counterparty_name": "ООО «Донские Поставки»",
                "source": "1c_enterprise",
                "note": "Счет на оплату № 104 от 1С:Бухгалтерия. Срок оплаты 5 дней"
            },
            {
                "id": f"1c_inv_{company_id}_102",
                "event_date": today + timedelta(days=12),
                "amount": 580000.0,  # Large buyer contract payment
                "probability": 0.85,
                "category_id": "cat_revenue_client",
                "counterparty_inn": "7701984512",
                "counterparty_name": "АО «Юг-Логистика»",
                "source": "1c_enterprise",
                "note": "Счет на оплату № 118 по договору поставки оборудования"
            },
            {
                "id": f"1c_inv_{company_id}_201",
                "event_date": today + timedelta(days=8),
                "amount": -185000.0,  # Supplier invoice (outflow)
                "probability": 0.95,
                "category_id": "cat_procurement",
                "counterparty_inn": "6165991040",
                "counterparty_name": "ООО «ПромСнабжение»",
                "source": "1c_enterprise",
                "note": "Входящий счет поставщика № СФ-491 на сырье и материалы"
            }
        ]
        return mock_invoices

    def status(self, company_id: str) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "display_name": self.display_name,
            "status": "active",
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "api_endpoint": "http://1c.enterprise.local/trade/odata/standard.odata/",
            "events_added": 3,
            "version": "8.3.24.1548",
            "format": "1CClientBankExchange 1.03"
        }

def generate_1c_client_bank_exchange(
    company_name: str,
    company_inn: str,
    account_number: str,
    date_from: date,
    date_to: date,
    initial_balance: float,
    final_balance: float,
    operations: List[Dict[str, Any]]
) -> str:
    """
    Generates standard 1C text exchange file (1CClientBankExchange) according to FR-12.3:
    1C format specification version 1.03
    """
    lines = [
        "1CClientBankExchange",
        "ВерсияФормата=1.03",
        "Кодировка=Windows",
        f"Отправитель=Банк «Центр-Инвест»",
        f"Получатель=1С:Предприятие",
        f"ДатаСоздания={datetime.now().strftime('%d.%m.%Y')}",
        f"ВремяСоздания={datetime.now().strftime('%H:%M:%S')}",
        f"ДатаНачала={date_from.strftime('%d.%m.%Y')}",
        f"ДатаКонца={date_to.strftime('%d.%m.%Y')}",
        f"РасчСчет={account_number}",
        "СекцияРасчСчет",
        f"ДатаНачала={date_from.strftime('%d.%m.%Y')}",
        f"ДатаКонца={date_to.strftime('%d.%m.%Y')}",
        f"НачальныйОстаток={initial_balance:.2f}",
        f"ВсегоПоступило={sum(op['amount'] for op in operations if op.get('direction') == 'Поступление'):.2f}",
        f"ВсегоСписано={sum(op['amount'] for op in operations if op.get('direction') == 'Списание'):.2f}",
        f"КонечныйОстаток={final_balance:.2f}",
        "КонецРасчСчет"
    ]

    for i, op in enumerate(operations, 1):
        doc_type = "Платежное поручение"
        op_date = op['operation_date'].strftime('%d.%m.%Y') if isinstance(op['operation_date'], (date, datetime)) else str(op['operation_date'])
        lines.extend([
            f"СекцияДокумент={doc_type}",
            f"Номер={i}",
            f"Дата={op_date}",
            f"Сумма={op['amount']:.2f}",
            f"Плательщик={company_name if op.get('direction') == 'Списание' else op.get('counterparty_name', 'Контрагент')}",
            f"ПлательщикИНН={company_inn if op.get('direction') == 'Списание' else op.get('counterparty_inn', '')}",
            f"Получатель={op.get('counterparty_name', 'Контрагент') if op.get('direction') == 'Списание' else company_name}",
            f"ПолучательИНН={op.get('counterparty_inn', '') if op.get('direction') == 'Списание' else company_inn}",
            f"НазначениеПлатежа={op.get('payment_purpose', '')}",
            "КонецДокумента"
        ])

    lines.append("КонецФайла")
    return "\r\n".join(lines)
