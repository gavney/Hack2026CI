"""
Модуль парсинга банковских выписок и первичных документов:
- Sberbank PDF-выписки (СберБизнес / СберБанк Онлайн)
- Т-Банк PDF-выписки
- 1C:Предприятие (1CClientBankExchange .txt, .csv, .xlsx)
- Плоские банковские CSV выписки
- Первичные документы (InvoiceParser: счета, акты, чеки, расчетные листки)
- Договоры (ContractParser)
- Интеллектуальная защита персональных данных (ПДн) и извлечение НДС
"""
import io
import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Union
from datetime import datetime, date
import pandas as pd
import numpy as np

try:
    import pymupdf as fitz
except ImportError:
    import fitz

logger = logging.getLogger("StatementParsers")

STANDARD_BANK_COLUMNS = [
    'company_id', 'operation_id', 'operation_date', 'amount', 'direction',
    'counterparty_inn', 'counterparty_name', 'payment_purpose', 'balance_eod'
]


# =========================================================================
# 1. ОБЩИЕ ФУНКЦИИ АНОНИМИЗАЦИИ И ИЗВЛЕЧЕНИЯ НДС
# =========================================================================

def anonymize_text(text: str) -> str:
    """
    Интеллектуальная зачистка ПДн, сохраняющая бизнес-реквизиты (ИНН, ОГРН, р/с компаний 407...).
    Скрывает: паспорта РФ, СНИЛС, телефоны, email, карты, счета физлиц (40817, 423xx), адреса, в/у, госномера.
    """
    if not text:
        return ""

    # 1. СНИЛС (XXX-XXX-XXX XX) - обрабатывается до кода подразделения, чтобы не резать первую часть
    text = re.sub(r'(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}(?!\d)', '[СНИЛС СКРЫТ]', text)

    # 2. Паспорта РФ: (?<!ИНН) предотвращает скрытие 10-значного ИНН
    text = re.sub(
        r'(?i)(?<!\d)(?<!ИНН )(?<!ИНН: )(?<!ИНН)\b\d{2}[\s\-]*\d{2}[\s\-]*\d{6}\b(?!\d)',
        '[ПАСПОРТ СКРЫТ]',
        text
    )
    text = re.sub(r'(?<!\d)(?<!\d{3}-)\d{3}-\d{3}(?!\d)(?![-\s]?\d{3})', '[КОД ПОДРАЗДЕЛЕНИЯ СКРЫТ]', text)
    text = re.sub(r'(?i)(паспорт выдан|выдан|кем выдан)[:\s]+(.*?)(?=(?:,\s*код|\s*\[|\n|$))', r'\1: [ОРГАН ВЫДАЧИ СКРЫТ] ', text)

    # 3. Контакты (Телефоны РФ и Email)
    text = re.sub(r'(?<!\d)\d{2,3}-\d{2}-\d{2}(?!\d)', '[ТЕЛЕФОН СКРЫТ]', text)
    text = re.sub(r'(?<!\d)(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)', '[ТЕЛЕФОН СКРЫТ]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b', '[EMAIL СКРЫТ]', text)

    # 4. Банковские карты (16-19 цифр)
    text = re.sub(r'(?<!\d)(?:\d{4}[-\s]?){3}\d{4,7}(?!\d)', '[КАРТА СКРЫТА]', text)

    # 5. Счета физлиц (40817, 423xx, 426xx - 20 цифр; счета юрлиц 407xx остаются нетронутыми!)
    accounts_pattern = r'(?<!\d)(?:40817|42301|42302|42303|42304|42305|42306|42307|42601|42602|42603|42604|42605|42606|42607)\d{15}(?!\d)'
    text = re.sub(accounts_pattern, '[СЧЕТ ФИЗЛИЦА СКРЫТ]', text)

    # 6. Демография и адреса проживания/доставки физлиц
    text = re.sub(r'(?i)(дата рождения|д\.р\.)[\s:]*([0-3]\d\.[0-1]\d\.\d{4}|\d{2}\s+[а-яА-Я]+\s+\d{4}\s*г?\.?)', r'\1: [ДАТА РОЖДЕНИЯ СКРЫТА]', text)
    text = re.sub(r'(?i)(место рождения|м\.р\.)[\s:]+[А-Яа-я\s\-\.,]+', r'\1: [МЕСТО РОЖДЕНИЯ СКРЫТО]', text)
    address_keywords = r'(адрес доставки|зарегистрирован(?:а|ный)? по адресу|проживающ(?:ий|ая) по адресу|адрес регистрации|место жительства|фактический адрес|прописан(?:а)?)'
    text = re.sub(rf'{address_keywords}[:\s]+[^\n]+', r'\1: [АДРЕС СКРЫТ]', text, flags=re.IGNORECASE)

    # 7. Транспорт (в/у и госномера)
    text = re.sub(r'(?i)(в/у|водительское удостоверение)[\s:]*(?<!\d)\d{2}\s*[А-Яа-яA-Za-z0-9]{2}\s*\d{6}(?!\d)', r'\1: [В/У СКРЫТО]', text)
    text = re.sub(r'(?<![А-Яа-яA-Za-z])[АВЕКМНОРСТУХABEKMHOPCTYX]\s*\d{3}\s*[АВЕКМНОРСТУХABEKMHOPCTYX]{2}\s*\d{2,3}(?![А-Яа-яA-Za-z])', '[ГОСНОМЕР СКРЫТ]', text, flags=re.IGNORECASE)

    return text


def clean_text_and_extract_vat(df: pd.DataFrame) -> pd.DataFrame:
    """
    Извлекает сумму НДС (vat_amount) и формирует очищенный текст для ML/AI категоризации.
    """
    if df.empty or 'payment_purpose' not in df.columns:
        return df

    vat_pattern = r'(?:в\s+т\.?ч\.?|в\s+том\s+числе|включая)?\s*ндс\s*(?:\(?\s*\d+\s*%\s*\)?)?\s*[-–—:]?\s*(\d+[\d\s\xa0]*[,\.]\d{2})'

    def extract_single_vat(val: Any) -> Optional[float]:
        s = str(val or "")
        m = re.search(vat_pattern, s, re.IGNORECASE)
        if m:
            clean_str = m.group(1).replace(' ', '').replace('\xa0', '').replace(',', '.')
            try:
                return float(clean_str)
            except Exception:
                return None
        return None

    df['vat_amount'] = df['payment_purpose'].apply(extract_single_vat)

    def clean_for_ai(text: str) -> str:
        text = str(text or "").lower()
        text = re.sub(r'(в т\.ч\.|в том числе|без налога|ндс не облагается|без ндс).*', '', text)
        text = re.sub(r'\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}г?\.?\b', '', text)
        text = re.sub(r'\bза\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-я]*\s+\d{4}\s*г?\.?\b', '', text)
        text = re.sub(r'(№|номер|л/с|лицевому счету|лицевой счет)\s*[\w\-\/]+', '', text)
        text = re.sub(r'\d+', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    df['clean_purpose'] = df['payment_purpose'].apply(clean_for_ai)
    return df


# =========================================================================
# 2. ПАРСЕР ВЫПИСОК СБЕРБАНКА (PDF)
# =========================================================================

class PdfStatementIntegration:
    """
    Коннектор для PDF-выписок Сбера (СберБизнес и СберБанк Онлайн).
    Поддерживает потоковую загрузку из памяти (bytes) и файлы на диске.
    """
    def __init__(self, file_path_or_bytes: Union[str, Path, bytes]):
        self.file_input = file_path_or_bytes
        self.raw_text = ""

    def _extract_text(self):
        try:
            if isinstance(self.file_input, bytes):
                doc = fitz.open(stream=self.file_input, filetype="pdf")
            else:
                p = Path(self.file_input)
                if not p.exists():
                    logger.error(f"Файл выписки Сбера не найден: {p}")
                    return
                doc = fitz.open(p)

            for page in doc:
                self.raw_text += page.get_text("text") + "\n"
        except Exception as e:
            logger.error(f"Ошибка чтения PDF Сбера: {e}")

    def _anonymize_sber_headers(self, text: str) -> str:
        if "Расшифровка операций" in text:
            text = text[text.find("Расшифровка операций"):]

        text = re.sub(r'Продолжение на следующей странице', '', text)
        text = re.sub(r'Для проверки подлинности документа.*?указанных в документе', '', text, flags=re.DOTALL)
        text = re.sub(r'Действителен\s+до\s+\d{2}\.\d{2}\.\d{4}', '', text)
        text = re.sub(r'www\.sberbank\.ru', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Выписка по платёжному счёту', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Страница \d+\s+из\s+\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'ДАТА ОПЕРАЦИИ \(МСК\)', '', text)
        text = re.sub(r'Дата обработки.*?и код авторизации', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'КАТЕГОРИЯ', '', text)
        text = re.sub(r'Описание операции', '', text, flags=re.IGNORECASE)
        text = re.sub(r'СУММА В ВАЛЮТЕ СЧЁТА', '', text)
        text = re.sub(r'Сумма в валюте.*?операции.?', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'ОСТАТОК СРЕДСТВ', '', text)
        text = re.sub(r'В валюте сч[её]та', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n\s*\n', '\n', text)
        text = anonymize_text(text)
        return text

    def parse_transactions(self) -> Optional[pd.DataFrame]:
        self._extract_text()
        if not self.raw_text:
            return None

        safe_text = self._anonymize_sber_headers(self.raw_text)

        # 1. Сбербанк Онлайн / Выписка по карте или счету
        pattern = re.compile(
            r'(\d{2}\.\d{2}\.\d{4})\n(.*?)\n(.*?)\n(.*?Операция по.*?\n?)((?:\+|-)?\d{1,3}(?:[ \s\xa0]\d{3})*,\d{2})',
            re.DOTALL | re.IGNORECASE
        )
        matches = pattern.findall(safe_text)
        parsed_data = []

        if matches:
            for match in matches:
                date_str, _, category, description, amount_str = [m.strip() for m in match]
                clean_amount_str = amount_str.replace(' ', '').replace('\xa0', '').replace(',', '.')
                direction = 'Поступление' if '+' in clean_amount_str else 'Списание'
                amount = abs(float(clean_amount_str.replace('+', '')))
                full_purpose = f"{category}. {description}".replace('\n', ' ')
                full_purpose = re.sub(r'\.?\s*Операция по (карте|счету)\s*\*+\d+.*', '', full_purpose, flags=re.IGNORECASE).strip()

                parsed_data.append({
                    'operation_date': date_str,
                    'amount': amount,
                    'direction': direction,
                    'payment_purpose': full_purpose,
                    'counterparty_name': category,
                    'counterparty_inn': None,
                })
        else:
            # 2. СберБизнес: Табличные строки с датой и суммами
            # Формат: DD.MM.YYYY ... Сумма дебет/кредит
            biz_pattern = re.compile(
                r'(\d{2}\.\d{2}\.\d{4})\s+([\d\w\-]+)?\s+([^\n]+?)\s+((?:\+|-)?\d{1,3}(?:[ \s\xa0]\d{3})*[\.,]\d{2})',
                re.MULTILINE
            )
            for m in biz_pattern.finditer(safe_text):
                d_str, doc_num, purpose, amt_str = m.groups()
                clean_amt = amt_str.replace(' ', '').replace('\xa0', '').replace(',', '.')
                direction = 'Поступление' if '+' in clean_amt else 'Списание'
                try:
                    amount = abs(float(clean_amt.replace('+', '')))
                    parsed_data.append({
                        'operation_date': d_str,
                        'amount': amount,
                        'direction': direction,
                        'payment_purpose': purpose.strip(),
                        'counterparty_name': None,
                        'counterparty_inn': None,
                    })
                except Exception:
                    pass

        if not parsed_data:
            return None

        df = pd.DataFrame(parsed_data)
        df['operation_date'] = pd.to_datetime(df['operation_date'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['operation_date'])
        df['source'] = 'PDF_Sber'
        return df

    def process(self) -> pd.DataFrame:
        df = self.parse_transactions()
        if df is None or df.empty:
            return pd.DataFrame()
        return clean_text_and_extract_vat(df)


# =========================================================================
# 3. ПАРСЕР ВЫПИСОК Т-БАНКА (PDF)
# =========================================================================

class TBankPdfIntegration:
    """Коннектор для PDF-выписок Т-Банка."""
    def __init__(self, file_path_or_bytes: Union[str, Path, bytes]):
        self.file_input = file_path_or_bytes
        self.raw_text = ""

    def _extract_text(self):
        try:
            if isinstance(self.file_input, bytes):
                doc = fitz.open(stream=self.file_input, filetype="pdf")
            else:
                p = Path(self.file_input)
                if not p.exists():
                    return
                doc = fitz.open(p)
            for page in doc:
                self.raw_text += page.get_text("text") + "\n"
        except Exception as e:
            logger.error(f"Ошибка чтения PDF Т-Банка: {e}")

    def parse_transactions(self) -> Optional[pd.DataFrame]:
        self._extract_text()
        if not self.raw_text:
            return None

        safe_text = anonymize_text(self.raw_text)
        blocks = re.split(r'(?=\b\d{2}\.\d{2}\.\d{4}\b)', safe_text)

        parsed_data = []
        for block in blocks:
            if not block.strip():
                continue
            date_match = re.search(r'^(\d{2}\.\d{2}\.\d{4})', block)
            if not date_match:
                continue

            amount_match = re.search(r'([+-][ \d\xa0]+[\.,]\d{2})', block)
            if not amount_match:
                continue

            amount_str = amount_match.group(1).replace(' ', '').replace('\xa0', '').replace(',', '.')
            direction = 'Поступление' if '+' in amount_str else 'Списание'
            amount = abs(float(amount_str.replace('+', '')))

            desc = block
            desc = re.sub(r'\b\d{2}\.\d{2}\.\d{4}\b', '', desc)
            desc = re.sub(r'\b\d{2}:\d{2}\b', '', desc)
            desc = re.sub(r'[+-][ \d\xa0]+[\.,]\d{2}(?:\s*[PР₽])?', '', desc)
            desc = re.sub(r'\b\d{4}\b', '', desc)
            desc = re.sub(r'\|', '', desc)
            desc = re.sub(r'Оплата в', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'Внутренний перевод на договор', 'Перевод', desc, flags=re.IGNORECASE)
            desc = re.sub(r'Внешний перевод по номеру телефона', 'Перевод', desc, flags=re.IGNORECASE)
            desc = re.sub(r'Пополнение\. Система быстрых платежей', 'СБП Пополнение', desc, flags=re.IGNORECASE)
            desc = re.sub(r'\s+', ' ', desc).strip()

            if len(desc) < 3:
                continue

            parsed_data.append({
                'operation_date': date_match.group(1),
                'amount': amount,
                'direction': direction,
                'payment_purpose': desc,
                'counterparty_name': None,
                'counterparty_inn': None,
                'source': 'TBank_PDF'
            })

        if not parsed_data:
            return None

        df = pd.DataFrame(parsed_data)
        df['operation_date'] = pd.to_datetime(df['operation_date'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['operation_date'])
        return clean_text_and_extract_vat(df)


# =========================================================================
# 4. ПАРСЕР ФАЙЛОВ 1C (1CClientBankExchange .txt, .csv, .xlsx)
# =========================================================================

class OneCFileIntegration:
    """Коннектор для выгрузок 1С:Предприятие (TXT ClientBank, CSV, Excel)."""
    def __init__(self, file_path_or_bytes: Union[str, Path, bytes], filename: str = "1c_export.txt"):
        self.file_input = file_path_or_bytes
        self.filename = filename

    def _get_text(self) -> str:
        if isinstance(self.file_input, bytes):
            raw_bytes = self.file_input
        else:
            with open(self.file_input, 'rb') as f:
                raw_bytes = f.read()

        for enc in ['windows-1251', 'utf-8-sig', 'utf-8', 'cp866']:
            try:
                return raw_bytes.decode(enc)
            except Exception:
                continue
        return raw_bytes.decode('windows-1251', errors='ignore')

    def parse_txt_client_bank(self, company_inn: Optional[str] = None) -> pd.DataFrame:
        text = self._get_text()
        lines = text.splitlines()

        transactions = []
        current_tx = {}
        in_document = False

        for line in lines:
            line = line.strip()
            if line.startswith('СекцияДокумент='):
                in_document = True
                current_tx = {'ТипДокумента': line.split('=', 1)[1] if '=' in line else 'Платеж'}
                continue
            if line.startswith('КонецДокумента') and in_document:
                in_document = False
                transactions.append(current_tx)
                current_tx = {}
                continue
            if in_document and '=' in line:
                key, value = line.split('=', 1)
                current_tx[key.strip()] = value.strip()

        if not transactions:
            return pd.DataFrame()

        df_raw = pd.DataFrame(transactions)
        rows = []

        for _, row in df_raw.iterrows():
            amt_str = str(row.get('Сумма', '0')).replace(' ', '').replace(',', '.')
            try:
                amt = abs(float(amt_str))
            except Exception:
                continue

            # Дата
            d_val = row.get('Дата') or row.get('ДатаСписано') or row.get('ДатаПоступило') or ''
            
            # Направление и контрагент
            payer_inn = str(row.get('ПлательщикИНН', '')).strip()
            recip_inn = str(row.get('ПолучательИНН', '')).strip()
            payer_name = str(row.get('Плательщик', '')).strip()
            recip_name = str(row.get('Получатель', '')).strip()

            has_incoming = bool(row.get('ДатаПоступило'))
            has_outgoing = bool(row.get('ДатаСписано'))

            if company_inn and payer_inn == str(company_inn):
                direction = 'Списание'
                cp_inn = recip_inn
                cp_name = recip_name
            elif company_inn and recip_inn == str(company_inn):
                direction = 'Поступление'
                cp_inn = payer_inn
                cp_name = payer_name
            elif has_incoming and not has_outgoing:
                direction = 'Поступление'
                cp_inn = payer_inn
                cp_name = payer_name
            else:
                direction = 'Списание'
                cp_inn = recip_inn
                cp_name = recip_name

            purpose = str(row.get('НазначениеПлатежа', '')).strip()

            rows.append({
                'operation_id': str(row.get('Номер', '')).strip() or None,
                'operation_date': d_val,
                'amount': amt,
                'direction': direction,
                'counterparty_inn': cp_inn or None,
                'counterparty_name': cp_name or None,
                'payment_purpose': purpose,
                'source': '1C_ClientBank'
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df['operation_date'] = pd.to_datetime(df['operation_date'], dayfirst=True, errors='coerce')
            df = df.dropna(subset=['operation_date'])
        return clean_text_and_extract_vat(df)

    def process(self, company_inn: Optional[str] = None) -> pd.DataFrame:
        ext = os.path.splitext(self.filename)[1].lower()
        if ext in ['.txt', '']:
            return self.parse_txt_client_bank(company_inn)
        elif ext == '.csv':
            if isinstance(self.file_input, bytes):
                buf = io.BytesIO(self.file_input)
            else:
                buf = self.file_input
            df = pd.read_csv(buf, sep=';', dtype=str)
            df['operation_date'] = pd.to_datetime(df.get('ДатаОплаты', df.get('Дата', df.get('operation_date'))), dayfirst=True, errors='coerce')
            df['amount'] = df.get('Сумма', df.get('amount', '0')).astype(str).str.replace(' ', '').str.replace(',', '.').astype(float)
            df['direction'] = df.get('direction', 'Списание')
            df['counterparty_inn'] = df.get('Контрагент_ИНН', df.get('ИНН', df.get('counterparty_inn', None)))
            df['counterparty_name'] = df.get('Контрагент', df.get('counterparty_name', None))
            df['payment_purpose'] = df.get('НазначениеПлатежа', df.get('payment_purpose', ''))
            return clean_text_and_extract_vat(df.dropna(subset=['operation_date']))
        elif ext in ['.xlsx', '.xls']:
            if isinstance(self.file_input, bytes):
                buf = io.BytesIO(self.file_input)
            else:
                buf = self.file_input
            df = pd.read_excel(buf, dtype=str)
            df['operation_date'] = pd.to_datetime(df.get('ДатаОплаты', df.get('Дата', df.get('operation_date'))), dayfirst=True, errors='coerce')
            df['amount'] = df.get('Сумма', df.get('amount', '0')).astype(str).str.replace(' ', '').str.replace(',', '.').astype(float)
            df['direction'] = df.get('direction', 'Списание')
            df['counterparty_inn'] = df.get('Контрагент_ИНН', df.get('ИНН', df.get('counterparty_inn', None)))
            df['counterparty_name'] = df.get('Контрагент', df.get('counterparty_name', None))
            df['payment_purpose'] = df.get('НазначениеПлатежа', df.get('payment_purpose', ''))
            return clean_text_and_extract_vat(df.dropna(subset=['operation_date']))
        return pd.DataFrame()


# =========================================================================
# 5. ПАРСЕР ПЕРВИЧНЫХ ДОКУМЕНТОВ (InvoiceParser)
# =========================================================================

class InvoiceParser:
    """
    Универсальный парсер первичных документов: накладные, счета, чеки, расчетные листки.
    Извлекает текст с сортировкой блоков и глубокой анонимизацией ПДн.
    """
    def __init__(self, file_path_or_bytes: Union[str, Path, bytes]):
        self.file_input = file_path_or_bytes

    def extract_smart_text(self, debug: bool = False) -> str:
        try:
            if isinstance(self.file_input, bytes):
                doc = fitz.open(stream=self.file_input, filetype="pdf")
            else:
                doc = fitz.open(Path(self.file_input))

            extracted_text = ""
            for page in doc:
                blocks = page.get_text("blocks")
                blocks.sort(key=lambda b: (b[1], b[0]))
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text:
                        extracted_text += block_text + "\n"

            safe_text = anonymize_text(extracted_text)
            return safe_text
        except Exception as e:
            logger.error(f"Ошибка чтения PDF документа: {e}")
            return ""


# =========================================================================
# 6. ПАРСЕР ДОГОВОРОВ (ContractParser)
# =========================================================================

class ContractParser:
    """
    Умный парсер для договоров: вытаскивает суть и реквизиты со страниц 0, 1 и двух последних,
    сохраняя структуру и анонимизируя персональные данные.
    """
    def __init__(self, file_path_or_bytes: Union[str, Path, bytes]):
        self.file_input = file_path_or_bytes

    def extract_smart_text(self, debug: bool = False) -> str:
        try:
            if isinstance(self.file_input, bytes):
                doc = fitz.open(stream=self.file_input, filetype="pdf")
            else:
                doc = fitz.open(Path(self.file_input))

            num_pages = len(doc)
            pages_to_read = list(range(num_pages)) if num_pages <= 5 else [0, 1, num_pages - 2, num_pages - 1]

            extracted_text = ""
            for page_num in pages_to_read:
                page = doc[page_num]
                blocks = page.get_text("blocks")
                blocks.sort(key=lambda b: (b[1], b[0]))
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text:
                        extracted_text += block_text + "\n"

            return anonymize_text(extracted_text)
        except Exception as e:
            logger.error(f"Ошибка чтения PDF договора: {e}")
            return ""


# =========================================================================
# 7. ЕДИНЫЙ ДИСПЕТЧЕР ИМПОРТА (parse_any_statement)
# =========================================================================

def parse_any_statement(
    content_bytes: bytes,
    filename: str,
    company_inn: Optional[str] = None,
    initial_balance: float = 0.0
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Автоматически распознает формат входного файла:
    - Sberbank PDF / T-Bank PDF
    - 1C TXT (1CClientBankExchange)
    - CSV выписка (стандартная с разделителем ';')
    - Excel (.xlsx, .xls)
    Возвращает нормализованный DataFrame со всеми обязательными полями радара:
    ['operation_id', 'operation_date', 'amount', 'direction', 'counterparty_inn',
     'counterparty_name', 'payment_purpose', 'balance_eod', 'vat_amount']
    и отчет о качестве данных (Quality Report).
    """
    ext = os.path.splitext(filename)[1].lower()
    df: Optional[pd.DataFrame] = None

    # 1. Проверка на PDF (по расширению или сигнатуре %PDF)
    is_pdf = ext == '.pdf' or content_bytes.startswith(b'%PDF')

    if is_pdf:
        # Проверяем, Сбербанк или Т-Банк
        try:
            sample_doc = fitz.open(stream=content_bytes, filetype="pdf")
            sample_text = ""
            for p_idx in range(min(3, len(sample_doc))):
                sample_text += sample_doc[p_idx].get_text("text")

            if "сбер" in sample_text.lower() or "sberbank" in sample_text.lower() or "расшифровка операций" in sample_text.lower():
                sber_parser = PdfStatementIntegration(content_bytes)
                df = sber_parser.process()
            elif "т-банк" in sample_text.lower() or "тинькофф" in sample_text.lower() or "tbank" in sample_text.lower():
                tbank_parser = TBankPdfIntegration(content_bytes)
                df = tbank_parser.parse_transactions()
            else:
                # По умолчанию пробуем парсер Сбера как наиболее универсальный
                sber_parser = PdfStatementIntegration(content_bytes)
                df = sber_parser.process()
        except Exception as e:
            logger.error(f"Ошибка определения структуры PDF: {e}")

    # 2. Проверка на 1C ClientBankExchange (TXT)
    elif ext == '.txt' or b'1CClientBankExchange' in content_bytes[:500]:
        onec = OneCFileIntegration(content_bytes, filename)
        df = onec.process(company_inn)

    # 3. Excel (.xlsx, .xls)
    elif ext in ['.xlsx', '.xls']:
        onec = OneCFileIntegration(content_bytes, filename)
        df = onec.process(company_inn)

    # 4. CSV (стандартный или банковский)
    if df is None or df.empty:
        # Пробуем декодировать текст
        text_content = None
        for enc in ['utf-8-sig', 'utf-8', 'cp1251', 'windows-1251', 'latin1']:
            try:
                text_content = content_bytes.decode(enc)
                break
            except Exception:
                pass

        if text_content:
            from backend.core.cleaning import parse_operations_csv
            buf = io.StringIO(text_content)
            try:
                clean_df, qr = parse_operations_csv(buf)
                if not clean_df.empty:
                    clean_df = clean_text_and_extract_vat(clean_df)
                    if "clean_rows" not in qr:
                        qr["clean_rows"] = len(clean_df)
                    if "initial_rows" not in qr:
                        qr["initial_rows"] = qr.get("initial_count", len(clean_df))
                    if "duplicates_count" not in qr:
                        qr["duplicates_count"] = qr.get("duplicate_count", 0)
                    return clean_df, qr
            except Exception:
                pass

    if df is None or df.empty:
        raise ValueError(f"Не удалось распознать формат файла '{filename}' или в нем отсутствуют транзакции.")

    # 5. Нормализация полей к стандарту Cashflow Radar
    if 'operation_id' not in df.columns or df['operation_id'].isna().all():
        df['operation_id'] = [f"op_{i+1:05d}" for i in range(len(df))]

    if 'counterparty_inn' not in df.columns:
        df['counterparty_inn'] = ''
    else:
        df['counterparty_inn'] = df['counterparty_inn'].fillna('').astype(str).str.strip()

    if 'counterparty_name' not in df.columns:
        df['counterparty_name'] = ''
    else:
        df['counterparty_name'] = df['counterparty_name'].fillna('').astype(str).str.strip()

    if 'payment_purpose' not in df.columns:
        df['payment_purpose'] = 'Банковская операция'
    else:
        df['payment_purpose'] = df['payment_purpose'].fillna('Банковская операция').astype(str).str.strip()

    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0).abs()

    # Нормализация направления
    def norm_dir(d_val: Any) -> str:
        s = str(d_val or '').lower()
        if s in ['поступление', 'приход', 'in', 'inflow', '+']:
            return 'Поступление'
        return 'Списание'

    df['direction'] = df['direction'].apply(norm_dir)
    df['operation_date'] = pd.to_datetime(df['operation_date'], errors='coerce')
    df = df.dropna(subset=['operation_date']).sort_values('operation_date').reset_index(drop=True)

    # 6. Расчет остатка (balance_eod), если он отсутствует
    if 'balance_eod' not in df.columns or df['balance_eod'].isna().all():
        curr_bal = float(initial_balance)
        bals = []
        for _, row in df.iterrows():
            amt = row['amount']
            if row['direction'] == 'Поступление':
                curr_bal += amt
            else:
                curr_bal -= amt
            bals.append(round(curr_bal, 2))
        df['balance_eod'] = bals
    else:
        df['balance_eod'] = pd.to_numeric(df['balance_eod'], errors='coerce').fillna(0.0)

    # 7. Дедупликация
    dedup_cols = ['operation_date', 'amount', 'direction', 'counterparty_inn', 'payment_purpose']
    duplicate_mask = df.duplicated(subset=dedup_cols, keep='first')
    df['is_duplicate'] = duplicate_mask
    clean_df = df[~duplicate_mask].copy().reset_index(drop=True)

    # 8. Отчет о качестве данных (Quality Report)
    total_count = len(clean_df)
    missing_inn = int((clean_df['counterparty_inn'] == '').sum())
    missing_purpose = int((clean_df['payment_purpose'] == '').sum())

    score = 100.0
    if total_count > 0:
        if (missing_inn / total_count) > 0.3:
            score -= 10.0
        if (missing_purpose / total_count) > 0.1:
            score -= 10.0

    qr = {
        "initial_rows": len(df),
        "clean_rows": total_count,
        "duplicates_count": int(duplicate_mask.sum()),
        "missing_inn_count": missing_inn,
        "missing_purpose_count": missing_purpose,
        "quality_score": round(max(50.0, score), 1),
        "source_format": clean_df.get('source', ['Standard'])[0] if 'source' in clean_df.columns else 'MultiFormat'
    }

    return clean_df, qr
