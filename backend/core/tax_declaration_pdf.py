"""
Генератор официальной налоговой декларации по УСН (Форма по КНД 1152017).
Соответствует официальному бланку ФНС России (Приказ ФНС России от 25.12.2020 № ЕД-7-3/958@):
- 4 оптических реперных черных квадрата по углам страниц (10x10 мм)
- Машиночитаемые штрих-коды Code 39 (0301 6015, 0301 6022 / 6039, 0301 6046 / 6084, 0301 6053 / 6091)
- Сетка знакомест с прочерками (-)
- Формирование полного комплекта сдаваемых листов:
  * Для УСН 6% (Доходы): Титульный лист, Раздел 1.1, Раздел 2.1.1 (Часть 1), Раздел 2.1.1 (Часть 2: страховые взносы)
  * Для УСН 15% (Доходы минус расходы): Титульный лист, Раздел 1.2, Раздел 2.2 (Часть 1), Раздел 2.2 (Часть 2: налог и минимальный налог)
"""
import io
import os
from typing import Dict, Any, List
import pymupdf as fitz

# Windows Font Paths
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf" if os.path.exists("C:/Windows/Fonts/arial.ttf") else None
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf" if os.path.exists("C:/Windows/Fonts/arialbd.ttf") else None
FONT_MONO = "C:/Windows/Fonts/cour.ttf" if os.path.exists("C:/Windows/Fonts/cour.ttf") else None
FONT_MONO_BOLD = "C:/Windows/Fonts/courbd.ttf" if os.path.exists("C:/Windows/Fonts/courbd.ttf") else None

# Таблица символов Code 39 (5 штрихов и 4 промежутка, ровно 3 широких 'W' и 6 узких 'N')
CODE39_PATTERNS = {
    '0': ('N', 'N', 'N', 'W', 'W', 'N', 'W', 'N', 'N'),
    '1': ('W', 'N', 'N', 'W', 'N', 'N', 'N', 'N', 'W'),
    '2': ('N', 'N', 'W', 'W', 'N', 'N', 'N', 'N', 'W'),
    '3': ('W', 'N', 'W', 'W', 'N', 'N', 'N', 'N', 'N'),
    '4': ('N', 'N', 'N', 'W', 'W', 'N', 'N', 'N', 'W'),
    '5': ('W', 'N', 'N', 'W', 'W', 'N', 'N', 'N', 'N'),
    '6': ('N', 'N', 'W', 'W', 'W', 'N', 'N', 'N', 'N'),
    '7': ('N', 'N', 'N', 'W', 'N', 'N', 'W', 'N', 'W'),
    '8': ('W', 'N', 'N', 'W', 'N', 'N', 'W', 'N', 'N'),
    '9': ('N', 'N', 'W', 'W', 'N', 'N', 'W', 'N', 'N'),
    '*': ('N', 'W', 'N', 'N', 'W', 'N', 'W', 'N', 'N')
}


def _format_cell_text(val: Any, length: int, pad_char: str = "-") -> str:
    """Форматирует строку под знакоместа с заполнением недостающих клеток прочерками."""
    s = str(val if val is not None else "").strip().upper()
    if len(s) > length:
        return s[:length]
    return s + (pad_char * (length - len(s)))


def _format_money_cells(val: Any, length: int) -> str:
    """Форматирует сумму в рублях для строк знакомест ФНС (без копеек, с прочерками в конце)."""
    if val is None or val == "":
        return "-" * length
    try:
        amt = int(round(float(val)))
        if amt < 0:
            amt = abs(amt)
        s = str(amt)
        if len(s) > length:
            return s[:length]
        return s + ("-" * (length - len(s)))
    except Exception:
        return "-" * length


def _draw_corner_squares(page: fitz.Page, w: float, h: float, margin: float = 14.17, sq_size: float = 14.17):
    """Отрисовка 4 черных оптических квадратов (реперов) по углам страницы (5x5 мм = 14.17 pt)."""
    # Верхний левый
    page.draw_rect(fitz.Rect(margin, margin, margin + sq_size, margin + sq_size), color=(0, 0, 0), fill=(0, 0, 0))
    # Верхний правый
    page.draw_rect(fitz.Rect(w - margin - sq_size, margin, w - margin, margin + sq_size), color=(0, 0, 0), fill=(0, 0, 0))
    # Нижний левый
    page.draw_rect(fitz.Rect(margin, h - margin - sq_size, margin + sq_size, h - margin), color=(0, 0, 0), fill=(0, 0, 0))
    # Нижний правый
    page.draw_rect(fitz.Rect(w - margin - sq_size, h - margin - sq_size, w - margin, h - margin), color=(0, 0, 0), fill=(0, 0, 0))


def _draw_barcode(page: fitz.Page, code_str: str, x: float = 38.0, y: float = 14.0, height: float = 22.0, narrow: float = 0.52, wide: float = 1.30):
    """
    Отрисовка эталонного машиночитаемого штрих-кода Code 39 по стандарту ФНС (ширина ~75 pt).
    Каждый символ имеет 9 чередующихся полос/промежутков с соотношением ширины 1:2.5.
    """
    clean = code_str.replace(" ", "")
    full_text = f"*{clean}*"
    cur_x = x
    for idx, ch in enumerate(full_text):
        pat = CODE39_PATTERNS.get(ch, CODE39_PATTERNS['0'])
        for i in range(9):
            is_bar = (i % 2 == 0)
            w = wide if pat[i] == 'W' else narrow
            if is_bar:
                page.draw_rect(fitz.Rect(cur_x, y, cur_x + w, y + height), color=(0, 0, 0), fill=(0, 0, 0))
            cur_x += w
        if idx < len(full_text) - 1:
            cur_x += narrow  # Межсимвольный интервал

    # Текст под штрих-кодом в официальном формате: "0301 6015"
    text_display = f"{clean[:4]} {clean[4:]}" if len(clean) == 8 else code_str
    if FONT_REGULAR:
        total_w = cur_x - x
        text_x = x + (total_w - 38.0) / 2.0
        page.insert_text(fitz.Point(text_x, y + height + 9.0), text_display, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8.0)


def _draw_cells(page: fitz.Page, text: str, x: float, y: float, count: int, cw: float = 12.0, ch: float = 14.5, pad: float = 1.5):
    """Отрисовка ряда знакомест (черные квадратные ячейки ФНС)."""
    chars = list(text)[:count]
    if len(chars) < count:
        chars += ["-"] * (count - len(chars))

    for i in range(count):
        cx = x + i * (cw + pad)
        page.draw_rect(fitz.Rect(cx, y, cx + cw, y + ch), color=(0, 0, 0), width=0.75)
        char = chars[i]
        if FONT_MONO_BOLD:
            page.insert_text(fitz.Point(cx + 2.5, y + 10.5), char, fontname="f_mono_b", fontfile=FONT_MONO_BOLD, fontsize=9.5)


def generate_tax_declaration_pdf(data: Dict[str, Any]) -> bytes:
    """
    Генерирует официальный сдаваемый комплект налоговой декларации УСН (КНД 1152017)
    в строгом соответствии с Приказом ФНС России от 25.12.2020 № ЕД-7-3/958@.
    Комплект состоит из 4 листов (Титульный + Раздел 1 + Раздел 2 часть 1 + Раздел 2 часть 2).
    """
    doc = fitz.open()
    w, h = 595.28, 841.89  # A4

    inn = str(data.get("inn", "")).strip()
    kpp = str(data.get("kpp", "")).strip()
    is_ip = len(inn) == 12 or data.get("legal_form", "").upper() == "ИП" or "ИП" in data.get("legal_form", "").upper()

    inn_cells = _format_cell_text(inn, 12)
    kpp_cells = _format_cell_text(kpp, 9) if not is_ip else "-" * 9
    tax_object = str(data.get("tax_object", "1")).strip()  # "1" = Доходы, "2" = Доходы минус расходы
    reporting_year = str(data.get("year", "2025")).strip()
    correction_num = _format_cell_text(str(data.get("correction_num", "0")), 3)
    period_code = _format_cell_text(str(data.get("period_code", "34")), 2)
    ifns_code = _format_cell_text(str(data.get("ifns_code", "7736")), 4)
    location_code = _format_cell_text(str(data.get("location_code", "120" if is_ip else "214")), 3)
    oktmo = _format_cell_text(str(data.get("oktmo", "45300000")), 11)
    phone = _format_cell_text(str(data.get("phone", "")), 20)
    company_name = str(data.get("company_name", "")).upper()

    is_6pct = (tax_object == "1")

    # =========================================================================
    # ЛИСТ 1: ТИТУЛЬНЫЙ ЛИСТ (Штрихкод 0301 6015, Стр. 001)
    # =========================================================================
    p1 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p1, w, h)
    _draw_barcode(p1, "0301 6015", x=38, y=14)

    # Верхний колонтитул
    p1.insert_text(fitz.Point(170, 25), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, inn_cells, 195, 14, 12)

    p1.insert_text(fitz.Point(170, 42), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, kpp_cells, 195, 31, 9)

    p1.insert_text(fitz.Point(375, 42), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, "001", 400, 31, 3)

    # Форма по КНД 1152017
    p1.insert_text(fitz.Point(440, 56), "Форма по КНД 1152017", fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.0)

    # Заголовок декларации
    title_text = "Налоговая декларация по налогу, уплачиваемому\nв связи с применением упрощенной системы налогообложения"
    p1.insert_text(fitz.Point(140, 88), title_text, fontname="f_bld", fontfile=FONT_BOLD, fontsize=10.0)

    # Сетка параметров периода и налогового органа
    y = 120
    p1.insert_text(fitz.Point(60, y + 8), "Номер корректировки", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, correction_num, 160, y, 3)

    p1.insert_text(fitz.Point(235, y + 8), "Налоговый период (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, period_code, 340, y, 2)

    p1.insert_text(fitz.Point(395, y + 8), "Отчетный год", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, reporting_year, 465, y, 4)

    y += 24
    p1.insert_text(fitz.Point(60, y + 8), "Представляется в налоговый орган (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, ifns_code, 240, y, 4)

    p1.insert_text(fitz.Point(320, y + 8), "по месту нахождения (учета) (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, location_code, 475, y, 3)

    # Налогоплательщик (4 строки по 40 клеток)
    y += 28
    words = company_name.split()
    lines = ["", "", "", ""]
    line_idx = 0
    for w_item in words:
        if line_idx >= 4:
            break
        if len(lines[line_idx]) + len(w_item) + 1 <= 40:
            lines[line_idx] = (lines[line_idx] + " " + w_item).strip()
        else:
            line_idx += 1
            if line_idx < 4:
                lines[line_idx] = w_item

    for i in range(4):
        line_text = _format_cell_text(lines[i], 40)
        _draw_cells(p1, line_text, 60, y, 40, cw=10.2, ch=13.0, pad=1.5)
        y += 16

    p1.insert_text(fitz.Point(240, y + 2), "(налогоплательщик)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.5)
    y += 15

    # Номер контактного телефона
    p1.insert_text(fitz.Point(60, y + 8), "Номер контактного телефона", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, phone, 200, y, 20, cw=10.5, ch=13.5, pad=1.5)
    y += 24

    # Объект налогообложения
    p1.insert_text(fitz.Point(60, y + 8), "Объект налогообложения:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, tax_object, 185, y, 1)
    p1.insert_text(fitz.Point(210, y + 4), "1 – доходы\n2 – доходы, уменьшенные на величину расходов", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.8)
    y += 30

    # Количество страниц
    p1.insert_text(fitz.Point(60, y + 8), "На", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, "004", 80, y, 3)
    p1.insert_text(fitz.Point(135, y + 8), "страницах с приложением документов на", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, "---", 325, y, 3)
    p1.insert_text(fitz.Point(380, y + 8), "листах", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)

    # Подтверждение сведений (рамка внизу)
    y += 24
    box_w = (w - 120) / 2
    box_h = 240
    p1.draw_rect(fitz.Rect(60, y, 60 + box_w, y + box_h), color=(0, 0, 0), width=0.8)
    p1.draw_rect(fitz.Rect(60 + box_w, y, w - 60, y + box_h), color=(0, 0, 0), width=0.8)

    p1.insert_text(fitz.Point(70, y + 16), "Достоверность и полноту сведений, указанных", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.0)
    p1.insert_text(fitz.Point(70, y + 26), "в настоящей декларации, подтверждаю:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.0)
    p1.insert_text(fitz.Point(70, y + 42), "1 – налогоплательщик, 2 – представитель", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.8)
    _draw_cells(p1, "1" if is_ip else "1", 240, y + 32, 1, cw=11, ch=13)

    p1.insert_text(fitz.Point(70, y + 62), "(фамилия, имя, отчество полностью)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.5)
    signer_name = data.get("signer_name", company_name)
    s_lines = signer_name.split()[:3]
    sy = y + 75
    for s_item in s_lines:
        _draw_cells(p1, _format_cell_text(s_item, 20), 70, sy, 20, cw=8.5, ch=12, pad=1.0)
        sy += 16

    p1.insert_text(fitz.Point(70, y + 155), "Подпись ________________    Дата", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    import datetime
    today = datetime.date.today()
    date_str = today.strftime("%d%m%Y")
    _draw_cells(p1, date_str, 200, y + 144, 8, cw=8.5, ch=12, pad=1.0)

    # Правая колонка: Заполняется работником налогового органа
    rx = 60 + box_w + 10
    p1.insert_text(fitz.Point(rx, y + 16), "Заполняется работником налогового органа", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    p1.insert_text(fitz.Point(rx, y + 36), "Сведения о представлении декларации", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    p1.insert_text(fitz.Point(rx, y + 60), "Данная декларация представлена (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    _draw_cells(p1, "--", rx + 175, y + 50, 2, cw=10, ch=13)

    # =========================================================================
    # ЛИСТ 2: РАЗДЕЛ 1 (Штрихкод 0301 6022 для 6% / 0301 6039 для 15%, Стр. 002)
    # =========================================================================
    p2 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p2, w, h)
    barcode_p2 = "0301 6022" if is_6pct else "0301 6039"
    _draw_barcode(p2, barcode_p2, x=38, y=14)

    # Верхний колонтитул
    p2.insert_text(fitz.Point(170, 25), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, inn_cells, 195, 14, 12)
    p2.insert_text(fitz.Point(170, 42), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, kpp_cells, 195, 31, 9)
    p2.insert_text(fitz.Point(375, 42), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, "002", 400, 31, 3)

    sec1_title = "Раздел 1.1. Сумма налога (авансового платежа по налогу), подлежащая уплате (уменьшению) (объект – доходы)" if is_6pct else "Раздел 1.2. Сумма налога (авансового платежа), подлежащая уплате (уменьшению) (объект – доходы минус расходы)"
    p2.insert_text(fitz.Point(60, 78), sec1_title, fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.0)

    rows_p2 = [
        ("Код по ОКТМО", "010", oktmo),
        ("Сумма авансового платежа к уплате за I квартал", "020", _format_money_cells(data.get("due_q1", 0), 11)),
        ("Код по ОКТМО", "030", oktmo),
        ("Сумма авансового платежа к доплате за полугодие", "040", _format_money_cells(data.get("due_q2", 0), 11)),
        ("Сумма авансового платежа к уменьшению за полугодие", "050", _format_money_cells(data.get("dec_q2", 0), 11)),
        ("Код по ОКТМО", "060", oktmo),
        ("Сумма авансового платежа к доплате за 9 месяцев", "070", _format_money_cells(data.get("due_q3", 0), 11)),
        ("Сумма авансового платежа к уменьшению за 9 месяцев", "080", _format_money_cells(data.get("dec_q3", 0), 11)),
        ("Код по ОКТМО", "090", oktmo),
        ("Сумма налога, подлежащая доплате за налоговый период (год)", "100", _format_money_cells(data.get("due_year", 0), 11)),
        ("Сумма налога к уменьшению за налоговый период (год)", "110", _format_money_cells(data.get("dec_year", 0), 11)),
    ]

    if not is_6pct:
        rows_p2.append(("Сумма минимального налога к уплате за налоговый период", "120", _format_money_cells(data.get("min_tax", 0), 11)))

    cur_y = 105
    for label, code, val_str in rows_p2:
        p2.insert_text(fitz.Point(60, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.2)
        p2.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p2, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 24

    # Подпись и дата внизу листа 2
    cur_y += 15
    p2.insert_text(fitz.Point(60, cur_y), "Достоверность и полноту сведений, указанных на данной странице, подтверждаю:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.8)
    p2.insert_text(fitz.Point(60, cur_y + 16), "Подпись: ________________________               Дата: ____.____.________", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.2)

    # =========================================================================
    # ЛИСТ 3: РАЗДЕЛ 2 ЧАСТЬ 1 (Штрихкод 0301 6046 для 6% / 0301 6084 для 15%, Стр. 003)
    # =========================================================================
    p3 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p3, w, h)
    barcode_p3 = "0301 6046" if is_6pct else "0301 6084"
    _draw_barcode(p3, barcode_p3, x=38, y=14)

    # Верхний колонтитул
    p3.insert_text(fitz.Point(170, 25), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, inn_cells, 195, 14, 12)
    p3.insert_text(fitz.Point(170, 42), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, kpp_cells, 195, 31, 9)
    p3.insert_text(fitz.Point(375, 42), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, "003", 400, 31, 3)

    if is_6pct:
        # Раздел 2.1.1 (Лист 1)
        sec2_title = "Раздел 2.1.1. Расчет налога, уплачиваемого в связи с применением УСН (объект налогообложения – доходы)"
        p3.insert_text(fitz.Point(60, 78), sec2_title, fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.0)

        y = 100
        p3.insert_text(fitz.Point(60, y + 8), "Признак налогоплательщика (1 - выплаты физлицам, 2 - без выплат):", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, y + 8), "102", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        payer_code = str(data.get("payer_code", "2" if is_ip else "1"))
        _draw_cells(p3, payer_code, 395, y, 1, cw=11.5, ch=13.5)

        # Доходы нарастающим итогом
        p3.insert_text(fitz.Point(60, 128), "Сумма полученных доходов (налоговая база) нарастающим итогом:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        rows_inc = [
            ("за первый квартал", "110", _format_money_cells(data.get("income_q1", 0), 11)),
            ("за полугодие", "111", _format_money_cells(data.get("income_q2", 0), 11)),
            ("за девять месяцев", "112", _format_money_cells(data.get("income_q3", 0), 11)),
            ("за налоговый период (год)", "113", _format_money_cells(data.get("income_year", 0), 11)),
        ]
        cur_y = 142
        for label, code, val_str in rows_inc:
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
            cur_y += 20

        # Ставки налога
        cur_y += 5
        p3.insert_text(fitz.Point(60, cur_y + 8), "Налоговая ставка (%):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        rate_val = f"{float(data.get('rate', 6.0)):.1f}"
        rate_cells = _format_cell_text(rate_val, 4)
        for label, code in [("за первый квартал", "120"), ("за полугодие", "121"), ("за девять месяцев", "122"), ("за налоговый период", "123")]:
            cur_y += 18
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, rate_cells, 395, cur_y, 4, cw=11.5, ch=13.5, pad=1.2)

        # Обоснование применения ставки (стр. 124)
        cur_y += 22
        p3.insert_text(fitz.Point(60, cur_y + 8), "Обоснование применения налоговой ставки:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, cur_y + 8), "124", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p3, "----------------", 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        # Исчисленный налог
        cur_y += 24
        p3.insert_text(fitz.Point(60, cur_y + 8), "Сумма исчисленного налога (авансового платежа):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("за первый квартал (стр. 110 x стр. 120 / 100)", "130", _format_money_cells(data.get("tax_q1", 0), 11)),
            ("за полугодие (стр. 111 x стр. 121 / 100)", "131", _format_money_cells(data.get("tax_q2", 0), 11)),
            ("за девять месяцев (стр. 112 x стр. 122 / 100)", "132", _format_money_cells(data.get("tax_q3", 0), 11)),
            ("за налоговый период (год) (стр. 113 x стр. 123 / 100)", "133", _format_money_cells(data.get("tax_year", 0), 11)),
        ]:
            cur_y += 20
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.8)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

    else:
        # Раздел 2.2 (Лист 1 для 15%)
        sec2_title = "Раздел 2.2. Расчет налога, уплачиваемого в связи с применением УСН, и минимального налога (объект – доходы минус расходы)"
        p3.insert_text(fitz.Point(60, 78), sec2_title, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)

        # Доходы
        cur_y = 100
        p3.insert_text(fitz.Point(60, cur_y + 8), "Сумма полученных доходов нарастающим итогом:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("за первый квартал", "210", _format_money_cells(data.get("income_q1", 0), 11)),
            ("за полугодие", "211", _format_money_cells(data.get("income_q2", 0), 11)),
            ("за девять месяцев", "212", _format_money_cells(data.get("income_q3", 0), 11)),
            ("за налоговый период (год)", "213", _format_money_cells(data.get("income_year", 0), 11)),
        ]:
            cur_y += 18
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        # Расходы
        cur_y += 20
        p3.insert_text(fitz.Point(60, cur_y + 8), "Сумма произведенных расходов нарастающим итогом:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("за первый квартал", "220", _format_money_cells(data.get("expense_q1", 0), 11)),
            ("за полугодие", "221", _format_money_cells(data.get("expense_q2", 0), 11)),
            ("за девять месяцев", "222", _format_money_cells(data.get("expense_q3", 0), 11)),
            ("за налоговый период (год)", "223", _format_money_cells(data.get("expense_year", 0), 11)),
        ]:
            cur_y += 18
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        # Налоговая база
        cur_y += 20
        p3.insert_text(fitz.Point(60, cur_y + 8), "Налоговая база для исчисления налога (доходы - расходы > 0):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        base_q1 = max(0, float(data.get("income_q1", 0)) - float(data.get("expense_q1", 0)))
        base_q2 = max(0, float(data.get("income_q2", 0)) - float(data.get("expense_q2", 0)))
        base_q3 = max(0, float(data.get("income_q3", 0)) - float(data.get("expense_q3", 0)))
        base_year = max(0, float(data.get("income_year", 0)) - float(data.get("expense_year", 0)))
        for label, code, val in [
            ("за первый квартал", "240", base_q1),
            ("за полугодие", "241", base_q2),
            ("за девять месяцев", "242", base_q3),
            ("за налоговый период (год)", "243", base_year),
        ]:
            cur_y += 18
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, _format_money_cells(val, 11), 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        # Ставки налога
        cur_y += 20
        p3.insert_text(fitz.Point(60, cur_y + 8), "Налоговая ставка (%):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        rate_val = f"{float(data.get('rate', 15.0)):.1f}"
        for label, code in [("за первый квартал", "260"), ("за полугодие", "261"), ("за девять месяцев", "262"), ("за налоговый период", "263")]:
            cur_y += 16
            p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p3, _format_cell_text(rate_val, 4), 395, cur_y, 4, cw=11.5, ch=13.5, pad=1.2)

    # =========================================================================
    # ЛИСТ 4: РАЗДЕЛ 2 ЧАСТЬ 2 (Штрихкод 0301 6053 для 6% / 0301 6091 для 15%, Стр. 004)
    # =========================================================================
    p4 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p4, w, h)
    barcode_p4 = "0301 6053" if is_6pct else "0301 6091"
    _draw_barcode(p4, barcode_p4, x=38, y=14)

    # Верхний колонтитул
    p4.insert_text(fitz.Point(170, 25), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p4, inn_cells, 195, 14, 12)
    p4.insert_text(fitz.Point(170, 42), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p4, kpp_cells, 195, 31, 9)
    p4.insert_text(fitz.Point(375, 42), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p4, "004", 400, 31, 3)

    if is_6pct:
        # Лист 4 для УСН 6%: Раздел 2.1.1 (продолжение: страховые взносы стр. 140-162)
        p4.insert_text(fitz.Point(60, 78), "Раздел 2.1.1 (продолжение). Страховые взносы и вычеты, уменьшающие налог", fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.0)

        cur_y = 105
        p4.insert_text(fitz.Point(60, cur_y + 8), "Сумма страховых взносов, уменьшающая сумму исчисленного налога:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        deduct_rows = [
            ("за первый квартал", "140", _format_money_cells(data.get("deduct_q1", 0), 11)),
            ("за полугодие", "141", _format_money_cells(data.get("deduct_q2", 0), 11)),
            ("за девять месяцев", "142", _format_money_cells(data.get("deduct_q3", 0), 11)),
            ("за налоговый период (год)", "143", _format_money_cells(data.get("deduct_year", 0), 11)),
        ]
        for label, code, val_str in deduct_rows:
            cur_y += 24
            p4.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.2)
            p4.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p4, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        cur_y += 35
        p4.insert_text(fitz.Point(60, cur_y + 8), "Сумма страховых взносов, установленных ст. 430 НК РФ (для ИП):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("в совокупном фиксированном размере", "150", _format_money_cells(data.get("ins_fixed", 0), 11)),
            ("в размере 1% с доходов, превышающих 300 тыс. рублей", "160", _format_money_cells(data.get("ins_1pct", 0), 11)),
            ("в том числе за расчетный период текущего года", "161", _format_money_cells(data.get("ins_1pct_curr", 0), 11)),
            ("за расчетный период предыдущего года", "162", _format_money_cells(data.get("ins_1pct_prev", 0), 11)),
        ]:
            cur_y += 24
            p4.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p4.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p4, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

    else:
        # Лист 4 для УСН 15%: Раздел 2.2 (продолжение: налог, минимальный налог, взносы)
        p4.insert_text(fitz.Point(60, 78), "Раздел 2.2 (продолжение). Сумма исчисленного налога и минимального налога", fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.0)

        cur_y = 105
        p4.insert_text(fitz.Point(60, cur_y + 8), "Сумма исчисленного налога (авансового платежа):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("за первый квартал (стр. 240 x стр. 260 / 100)", "270", _format_money_cells(data.get("tax_q1", 0), 11)),
            ("за полугодие (стр. 241 x стр. 261 / 100)", "271", _format_money_cells(data.get("tax_q2", 0), 11)),
            ("за девять месяцев (стр. 242 x стр. 262 / 100)", "272", _format_money_cells(data.get("tax_q3", 0), 11)),
            ("за налоговый период (год) (стр. 243 x стр. 263 / 100)", "273", _format_money_cells(data.get("tax_year", 0), 11)),
        ]:
            cur_y += 24
            p4.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p4.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p4, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

        cur_y += 30
        p4.insert_text(fitz.Point(60, cur_y + 8), "Сумма исчисленного минимального налога за год (ставка 1% от доходов):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        p4.insert_text(fitz.Point(70, cur_y + 24), "стр. 213 x 1 / 100", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p4.insert_text(fitz.Point(360, cur_y + 24), "280", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p4, _format_money_cells(data.get("min_tax", 0), 11), 395, cur_y + 16, 11, cw=11.5, ch=13.5, pad=1.2)

        cur_y += 45
        p4.insert_text(fitz.Point(60, cur_y + 8), "Сумма страховых взносов ст. 430 НК РФ (для ИП):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        for label, code, val_str in [
            ("в совокупном фиксированном размере", "290", _format_money_cells(data.get("ins_fixed", 0), 11)),
            ("в размере 1% с доходов, превышающих 300 тыс. рублей", "300", _format_money_cells(data.get("ins_1pct", 0), 11)),
        ]:
            cur_y += 24
            p4.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
            p4.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
            _draw_cells(p4, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)

    # Save to buffer
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def get_company_tax_declaration_data(company, operations: list, year: int = None) -> Dict[str, Any]:
    """
    Рассчитывает исходные показатели декларации УСН за указанный год на основе операций компании.
    """
    from datetime import datetime
    
    if not year:
        # Определение года по последним операциям компании или текущий год
        if operations:
            dates = [op.operation_date for op in operations if getattr(op, "operation_date", None)]
            year = max(dates).year if dates else datetime.utcnow().year
        else:
            year = datetime.utcnow().year

    # Разделяем операции года по кварталам
    q1_ops = []
    q2_ops = []
    q3_ops = []
    q4_ops = []

    for op in operations:
        d = op.operation_date
        if not d or d.year != year:
            continue
        m = d.month
        if 1 <= m <= 3:
            q1_ops.append(op)
        elif 4 <= m <= 6:
            q2_ops.append(op)
        elif 7 <= m <= 9:
            q3_ops.append(op)
        elif 10 <= m <= 12:
            q4_ops.append(op)

    def calc_income(ops_list):
        return sum(
            op.amount for op in ops_list
            if (op.direction in ("Поступление", "inflow")) and op.category_id != "cat_transfer_own"
        )

    def calc_expense(ops_list):
        # Налогово учитываемые расходы для УСН 15%
        deduct_cats = {
            "cat_procurement", "cat_payroll", "cat_tax_enp",
            "cat_rent_utilities", "cat_bank_credit", "cat_services_marketing", "cat_transport"
        }
        return sum(
            op.amount for op in ops_list
            if (op.direction in ("Списание", "outflow")) and (not op.category_id or op.category_id in deduct_cats)
        )

    q1_inc = calc_income(q1_ops)
    q2_inc = calc_income(q2_ops)
    q3_inc = calc_income(q3_ops)
    q4_inc = calc_income(q4_ops)

    q1_exp = calc_expense(q1_ops)
    q2_exp = calc_expense(q2_ops)
    q3_exp = calc_expense(q3_ops)
    q4_exp = calc_expense(q4_ops)

    # Нарастающий итог доходов
    inc_q1 = round(q1_inc)
    inc_q2 = round(q1_inc + q2_inc)
    inc_q3 = round(q1_inc + q2_inc + q3_inc)
    inc_year = round(q1_inc + q2_inc + q3_inc + q4_inc)

    # Нарастающий итог расходов
    exp_q1 = round(q1_exp)
    exp_q2 = round(q1_exp + q2_exp)
    exp_q3 = round(q1_exp + q2_exp + q3_exp)
    exp_year = round(q1_exp + q2_exp + q3_exp + q4_exp)

    regime = (company.tax_regime or "УСН Доходы 6%").strip()
    is_15 = "15" in regime
    tax_object = "2" if is_15 else "1"
    rate = 15.0 if is_15 else 6.0

    if is_15:
        base_q1 = max(0, inc_q1 - exp_q1)
        base_q2 = max(0, inc_q2 - exp_q2)
        base_q3 = max(0, inc_q3 - exp_q3)
        base_year = max(0, inc_year - exp_year)
    else:
        base_q1 = inc_q1
        base_q2 = inc_q2
        base_q3 = inc_q3
        base_year = inc_year

    tax_q1 = round(base_q1 * rate / 100)
    tax_q2 = round(base_q2 * rate / 100)
    tax_q3 = round(base_q3 * rate / 100)
    tax_year = round(base_year * rate / 100)

    min_tax = round(inc_year * 0.01) if is_15 else 0

    # Расчет платежей Раздела 1
    due_q1 = tax_q1

    diff_q2 = tax_q2 - due_q1
    due_q2 = max(0, diff_q2)
    dec_q2 = abs(diff_q2) if diff_q2 < 0 else None

    prev_accrued = due_q1 + (due_q2 if due_q2 else -(dec_q2 or 0))
    diff_q3 = tax_q3 - prev_accrued
    due_q3 = max(0, diff_q3)
    dec_q3 = abs(diff_q3) if diff_q3 < 0 else None

    prev_accrued_year = prev_accrued + (due_q3 if due_q3 else -(dec_q3 or 0))
    final_tax = max(tax_year, min_tax) if is_15 else tax_year
    diff_year = final_tax - prev_accrued_year
    due_year = max(0, diff_year)
    dec_year = abs(diff_year) if diff_year < 0 else None

    clean_inn = str(company.inn or "").strip()
    is_ip = len(clean_inn) == 12 or (company.legal_form or "").upper() == "ИП" or "ИП" in (company.legal_form or "").upper()
    ifns_code = clean_inn[:4] if len(clean_inn) >= 4 and clean_inn[:4].isdigit() else "6164"

    return {
        "company_id": company.id,
        "company_name": company.name,
        "inn": clean_inn,
        "kpp": company.inn if not is_ip else "",
        "legal_form": company.legal_form or ("ИП" if is_ip else "ООО"),
        "year": year,
        "correction_num": "0",
        "period_code": "34",
        "ifns_code": ifns_code,
        "location_code": "120" if is_ip else "214",
        "oktmo": "60701000",
        "phone": "+7 (863) 200-00-00",
        "signer_name": company.name,
        "tax_regime": regime,
        "tax_object": tax_object,
        "rate": rate,
        "payer_code": "2" if is_ip else "1",
        "income_q1": inc_q1,
        "income_q2": inc_q2,
        "income_q3": inc_q3,
        "income_year": inc_year,
        "expense_q1": exp_q1,
        "expense_q2": exp_q2,
        "expense_q3": exp_q3,
        "expense_year": exp_year,
        "base_q1": base_q1,
        "base_q2": base_q2,
        "base_q3": base_q3,
        "base_year": base_year,
        "tax_q1": tax_q1,
        "tax_q2": tax_q2,
        "tax_q3": tax_q3,
        "tax_year": tax_year,
        "min_tax": min_tax,
        "due_q1": due_q1,
        "due_q2": due_q2,
        "dec_q2": dec_q2,
        "due_q3": due_q3,
        "dec_q3": dec_q3,
        "due_year": due_year,
        "dec_year": dec_year,
        "deduct_q1": 0,
        "deduct_q2": 0,
        "deduct_q3": 0,
        "deduct_year": 0,
        "ins_fixed": 53658 if is_ip else 0,
        "ins_1pct": max(0, round((inc_year - 300000) * 0.01)) if is_ip and inc_year > 300000 else 0,
        "ins_1pct_curr": max(0, round((inc_year - 300000) * 0.01)) if is_ip and inc_year > 300000 else 0,
        "ins_1pct_prev": 0
    }
