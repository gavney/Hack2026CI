import io
import pytest
import pandas as pd
from datetime import date
from backend.core.statement_parsers import (
    anonymize_text,
    clean_text_and_extract_vat,
    OneCFileIntegration,
    PdfStatementIntegration,
    TBankPdfIntegration,
    InvoiceParser,
    ContractParser,
    parse_any_statement
)


def test_anonymize_text():
    sample = (
        "Клиент Иванов И.И., паспорт 45 10 123456 выдан ОВД г. Москвы, код 100-001. "
        "СНИЛС 123-456-789 01, тел. +7 (999) 111-22-33, email test@domain.ru. "
        "Оплата с карты 4276 1234 5678 9012, счет 40817810000000123456. "
        "ИНН 7707329152, расчетный счет компании 40702810000000123456."
    )
    anon = anonymize_text(sample)

    assert "[ПАСПОРТ СКРЫТ]" in anon
    assert "[КОД ПОДРАЗДЕЛЕНИЯ СКРЫТ]" in anon
    assert "[СНИЛС СКРЫТ]" in anon
    assert "[ТЕЛЕФОН СКРЫТ]" in anon
    assert "[EMAIL СКРЫТ]" in anon
    assert "[КАРТА СКРЫТА]" in anon
    assert "[СЧЕТ ФИЗЛИЦА СКРЫТ]" in anon
    # Corporate INN and corporate settlement account 40702 must NOT be hidden
    assert "7707329152" in anon
    assert "40702810000000123456" in anon


def test_clean_text_and_extract_vat():
    df = pd.DataFrame([
        {"payment_purpose": "Оплата по счету №12. В том числе НДС 20% 5 400.50 руб. за поставку"},
        {"payment_purpose": "Услуги аренды. Без НДС"},
        {"payment_purpose": "Авансовый платеж по договору, в т.ч. НДС (20%) - 1200,00 руб."},
    ])

    processed = clean_text_and_extract_vat(df)
    assert 'vat_amount' in processed.columns
    assert 'clean_purpose' in processed.columns

    assert processed.iloc[0]['vat_amount'] == 5400.50
    assert pd.isna(processed.iloc[1]['vat_amount'])
    assert processed.iloc[2]['vat_amount'] == 1200.00
    assert "№" not in processed.iloc[0]['clean_purpose']


def test_onec_client_bank_exchange_parsing():
    content = """1CClientBankExchange
ВерсияФормата=1.03
Кодировка=Windows
Отправитель=Бухгалтерия
СекцияРасчСчет
ДатаНачала=01.01.2026
ДатаКонца=31.01.2026
РасчСчет=40702810000000000001
КонецРасчСчет
СекцияДокумент=Платежное поручение
Номер=101
Дата=15.01.2026
Сумма=45000.00
ПлательщикИНН=7707111222
Плательщик=ООО "Покупатель"
ПолучательИНН=7707333444
Получатель=ООО "Продавец"
ДатаСписано=15.01.2026
НазначениеПлатежа=Оплата за товар по счету 5. В т.ч. НДС 20% 7500.00
КонецДокумента
СекцияДокумент=Платежное поручение
Номер=102
Дата=20.01.2026
Сумма=120000.00
ПлательщикИНН=7707333444
Плательщик=ООО "Продавец"
ПолучательИНН=7707555666
Получатель=ООО "Поставщик"
ДатаСписано=20.01.2026
НазначениеПлатежа=Закупка оборудования. Без НДС
КонецДокумента
КонецФайла
"""
    raw_bytes = content.encode('windows-1251')
    parser = OneCFileIntegration(raw_bytes, "export.txt")
    df = parser.process(company_inn="7707333444")

    assert not df.empty
    assert len(df) == 2
    # Document 101 was paid TO our company (7707333444 is recipient) -> Поступление
    assert df.iloc[0]['direction'] == 'Поступление'
    assert df.iloc[0]['amount'] == 45000.00
    assert df.iloc[0]['counterparty_inn'] == '7707111222'
    assert df.iloc[0]['vat_amount'] == 7500.00

    # Document 102 was paid BY our company -> Списание
    assert df.iloc[1]['direction'] == 'Списание'
    assert df.iloc[1]['amount'] == 120000.00
    assert df.iloc[1]['counterparty_inn'] == '7707555666'


def test_parse_any_statement_csv():
    csv_content = (
        "company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod\n"
        "C001;op_1;2026-01-15;10000.00;Поступление;7707000001;ООО Альфа;Оплата за ПО. В т.ч. НДС 20% 1666.67;110000.00\n"
        "C001;op_2;2026-01-20;5000.00;Списание;7707000002;ООО Бета;Оплата хостинга;105000.00\n"
    ).encode('utf-8')

    df, qr = parse_any_statement(csv_content, "statement.csv")
    assert len(df) == 2
    assert qr["clean_rows"] == 2
    assert df.iloc[0]['vat_amount'] == 1666.67


def test_sberbank_pdf_integration_synthetic():
    sber_text = """
ПАО СБЕРБАНК
Выписка по платёжному счёту
Расшифровка операций
ДАТА ОПЕРАЦИИ (МСК)
ВРЕМЯ
КАТЕГОРИЯ
СУММА В ВАЛЮТЕ СЧЁТА
ОСТАТОК СРЕДСТВ

15.01.2026
14:20
Переводы
Операция по карте *1234
+25 000,00

18.01.2026
10:15
Супермаркеты
Операция по карте *1234
-3 500,50
"""
    parser = PdfStatementIntegration(b'%PDF-1.4 dummy')
    parser.raw_text = sber_text
    df = parser.process()

    assert not df.empty
    assert len(df) == 2
    assert df.iloc[0]['amount'] == 25000.00
    assert df.iloc[0]['direction'] == 'Поступление'
    assert df.iloc[1]['amount'] == 3500.50
    assert df.iloc[1]['direction'] == 'Списание'


def test_tbank_and_invoice_parsers():
    tbank = TBankPdfIntegration(b'%PDF-1.4 dummy')
    tbank.raw_text = """
Гарифулин Юрий Мансурович
Номер договора: 1234567890
15.01.2026 14:20 +10 000,00 ₽ Пополнение. Система быстрых платежей
20.01.2026 11:00 -2 500,00 ₽ Оплата в магазине Пятерочка
"""
    t_df = tbank.parse_transactions()
    assert not t_df.empty
    assert len(t_df) == 2
    assert t_df.iloc[0]['direction'] == 'Поступление'
    assert t_df.iloc[1]['direction'] == 'Списание'

    inv = InvoiceParser(b'')
    inv_anon = anonymize_text("Счет-фактура №1. Паспорт 45 10 123456.")
    assert "[ПАСПОРТ СКРЫТ]" in inv_anon

