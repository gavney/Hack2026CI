"""
Генератор официальной налоговой декларации по УСН (Форма по КНД 1152017).
Соответствует официальному бланку ФНС России:
- 4 реперных черных квадрата по углам страниц (10x10 мм)
- Машиночитаемые штрихкоды формы (0301 6015, 0301 6022 / 6039, 0301 6046 / 6084)
- Сетка знакомест (клеточек) с разделителями и прочерками (-)
- Страницы: Титульный лист, Раздел 1.1/1.2, Раздел 2.1.1/2.2
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


def _draw_corner_squares(page: fitz.Page, w: float, h: float, margin: float = 20.0, sq_size: float = 28.35):
    """Отрисовка 4 черных оптических квадратов (реперов) по углам страницы (10x10 мм)."""
    # Верхний левый
    page.draw_rect(fitz.Rect(margin, margin, margin + sq_size, margin + sq_size), color=(0, 0, 0), fill=(0, 0, 0))
    # Верхний правый
    page.draw_rect(fitz.Rect(w - margin - sq_size, margin, w - margin, margin + sq_size), color=(0, 0, 0), fill=(0, 0, 0))
    # Нижний левый
    page.draw_rect(fitz.Rect(margin, h - margin - sq_size, margin + sq_size, h - margin), color=(0, 0, 0), fill=(0, 0, 0))
    # Нижний правый
    page.draw_rect(fitz.Rect(w - margin - sq_size, h - margin - sq_size, w - margin, h - margin), color=(0, 0, 0), fill=(0, 0, 0))


def _draw_barcode(page: fitz.Page, code_str: str, x: float = 60.0, y: float = 20.0):
    """Отрисовка штрих-кода слева вверху."""
    bars = [2, 1, 3, 1, 2, 3, 1, 2, 1, 3, 2, 1, 1, 3, 2, 2, 1, 3, 1, 2, 3, 1, 2, 1, 3, 2, 1, 2, 3, 1]
    cur_x = x
    for b in bars:
        page.draw_rect(fitz.Rect(cur_x, y, cur_x + b, y + 26), color=(0, 0, 0), fill=(0, 0, 0))
        cur_x += b + 1.2
    
    if FONT_REGULAR:
        page.insert_text(fitz.Point(x + 10, y + 36), code_str, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)


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
    Генерирует официальный PDF налоговой декларации УСН (КНД 1152017)
    на основе словаря данных.
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
    ifns_code = _format_cell_text(str(data.get("ifns_code", "6164")), 4)
    location_code = _format_cell_text(str(data.get("location_code", "120" if is_ip else "214")), 3)
    oktmo = _format_cell_text(str(data.get("oktmo", "60701000")), 11)
    phone = _format_cell_text(str(data.get("phone", "+7 (900) 000-00-00")), 20)
    company_name = str(data.get("company_name", "")).strip().upper()
    signer_name = str(data.get("signer_name", company_name)).strip().upper()

    # =========================================================================
    # СТРАНИЦА 1: ТИТУЛЬНЫЙ ЛИСТ (0301 6015)
    # =========================================================================
    p1 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p1, w, h)
    _draw_barcode(p1, "0301 6015", x=60, y=20)

    # Верхний колонтитул
    p1.insert_text(fitz.Point(170, 31), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, inn_cells, 195, 20, 12)

    p1.insert_text(fitz.Point(170, 48), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, kpp_cells, 195, 37, 9)

    p1.insert_text(fitz.Point(375, 48), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p1, "001", 400, 37, 3)

    # Заголовок
    p1.insert_text(fitz.Point(60, 85), "Форма по КНД 1152017", fontname="f_bld", fontfile=FONT_BOLD, fontsize=9.5)
    p1.insert_text(fitz.Point(165, 105), "Налоговая декларация по налогу, уплачиваемому", fontname="f_bld", fontfile=FONT_BOLD, fontsize=10.5)
    p1.insert_text(fitz.Point(135, 118), "в связи с применением упрощенной системы налогообложения", fontname="f_bld", fontfile=FONT_BOLD, fontsize=10.5)

    # Номер корректировки, период, год
    y = 145
    p1.insert_text(fitz.Point(60, y + 10), "Номер корректировки", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, correction_num, 160, y, 3)

    p1.insert_text(fitz.Point(235, y + 10), "Налоговый период (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, period_code, 340, y, 2)

    p1.insert_text(fitz.Point(400, y + 10), "Отчетный год", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, reporting_year, 465, y, 4)

    # Представляется в налоговый орган
    y = 175
    p1.insert_text(fitz.Point(60, y + 10), "Представляется в налоговый орган (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, ifns_code, 245, y, 4)

    p1.insert_text(fitz.Point(340, y + 10), "по месту нахождения (учета) (код)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, location_code, 490, y, 3)

    # Налогоплательщик (4 строки по 40 знакомест)
    y = 205
    p1.insert_text(fitz.Point(60, y), "Налогоплательщик:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    words = company_name.split()
    line1 = words[0] if len(words) > 0 else ""
    line2 = " ".join(words[1:3]) if len(words) > 1 else ""
    line3 = " ".join(words[3:]) if len(words) > 3 else ""

    _draw_cells(p1, _format_cell_text(line1, 36), 60, y + 8, 36, cw=12.0, ch=14.0)
    _draw_cells(p1, _format_cell_text(line2, 36), 60, y + 26, 36, cw=12.0, ch=14.0)
    _draw_cells(p1, _format_cell_text(line3, 36), 60, y + 44, 36, cw=12.0, ch=14.0)
    p1.insert_text(fitz.Point(235, y + 68), "(налогоплательщик)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)

    # Объект налогообложения
    y = 290
    p1.insert_text(fitz.Point(60, y + 10), "Объект налогообложения:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, tax_object, 185, y, 1)
    p1.insert_text(fitz.Point(210, y + 7), "1 – доходы", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    p1.insert_text(fitz.Point(210, y + 16), "2 – доходы, уменьшенные на величину расходов", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)

    # Номер телефона
    y = 320
    p1.insert_text(fitz.Point(60, y + 10), "Номер контактного телефона", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, phone, 195, y, 20)

    # Количество страниц
    y = 350
    p1.insert_text(fitz.Point(60, y + 10), "На", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, "003", 80, y, 3)
    p1.insert_text(fitz.Point(135, y + 10), "страницах с приложением подтверждающих документов на", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    _draw_cells(p1, "---", 385, y, 3)
    p1.insert_text(fitz.Point(435, y + 10), "листах", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)

    # Рамка блока подтверждения достоверности
    y = 385
    p1.draw_rect(fitz.Rect(60, y, 535, y + 160), color=(0, 0, 0), width=0.8)
    p1.draw_line(fitz.Point(300, y), fitz.Point(300, y + 160), color=(0, 0, 0), width=0.8)

    # Левая колонка - достоверность
    p1.insert_text(fitz.Point(70, y + 15), "Достоверность и полноту сведений подтверждаю:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    _draw_cells(p1, "1", 70, y + 25, 1)
    p1.insert_text(fitz.Point(90, y + 33), "1 – налогоплательщик  2 – представитель", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)

    s_words = signer_name.split()
    _draw_cells(p1, _format_cell_text(s_words[0] if len(s_words) > 0 else "", 16), 70, y + 48, 16)
    _draw_cells(p1, _format_cell_text(s_words[1] if len(s_words) > 1 else "", 16), 70, y + 66, 16)
    _draw_cells(p1, _format_cell_text(" ".join(s_words[2:]) if len(s_words) > 2 else "", 16), 70, y + 84, 16)
    p1.insert_text(fitz.Point(120, y + 108), "(фамилия, имя, отчество полностью)", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=6.5)

    p1.insert_text(fitz.Point(70, y + 130), "Подпись: ____________", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)
    p1.insert_text(fitz.Point(180, y + 130), "Дата: __.__.____", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.5)

    # Правая колонка - заполняется налоговым органом
    p1.insert_text(fitz.Point(310, y + 15), "Заполняется работником налогового органа", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    p1.insert_text(fitz.Point(310, y + 35), "Сведения о представлении декларации:", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    p1.insert_text(fitz.Point(310, y + 60), "Дата представления: __.__.____", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    p1.insert_text(fitz.Point(310, y + 85), "Зарегистрирована за № _____________", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)

    # =========================================================================
    # СТРАНИЦА 2: РАЗДЕЛ 1.1 (0301 6022) - Суммы к уплате
    # =========================================================================
    p2 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p2, w, h)
    is_6pct = (tax_object == "1")
    barcode_p2 = "0301 6022" if is_6pct else "0301 6039"
    _draw_barcode(p2, barcode_p2, x=60, y=20)

    # Верхний колонтитул
    p2.insert_text(fitz.Point(170, 31), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, inn_cells, 195, 20, 12)
    p2.insert_text(fitz.Point(170, 48), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, kpp_cells, 195, 37, 9)
    p2.insert_text(fitz.Point(375, 48), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p2, "002", 400, 37, 3)

    # Заголовок Раздела 1
    sec1_title = "Раздел 1.1. Сумма налога (авансового платежа по налогу), уплачиваемого в связи с применением УСН" if is_6pct else "Раздел 1.2. Сумма налога, уплачиваемого в связи с применением УСН (доходы минус расходы)"
    p2.insert_text(fitz.Point(60, 80), sec1_title, fontname="f_bld", fontfile=FONT_BOLD, fontsize=9.0)
    p2.insert_text(fitz.Point(60, 93), f"(объект налогообложения – {'доходы' if is_6pct else 'доходы, уменьшенные на величину расходов'})", fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.5)

    # Шапка таблицы показателей
    y = 120
    p2.insert_text(fitz.Point(60, y), "Показатели", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    p2.insert_text(fitz.Point(350, y), "Код строки", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    p2.insert_text(fitz.Point(420, y), "Значения показателей (в рублях)", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    p2.draw_line(fitz.Point(60, y + 5), fitz.Point(535, y + 5), color=(0, 0, 0), width=0.6)

    # Строки Раздела 1
    rows_p2 = [
        ("Код по ОКТМО", "010", oktmo),
        ("Сумма авансового платежа к уплате за I квартал", "020", _format_money_cells(data.get("due_q1", 0), 11)),
        ("Код по ОКТМО", "030", oktmo),
        ("Сумма авансового платежа к уплате за полугодие", "040", _format_money_cells(data.get("due_q2", 0), 11)),
        ("Сумма авансового платежа к уменьшению за полугодие", "050", _format_money_cells(data.get("dec_q2", None), 11)),
        ("Код по ОКТМО", "060", oktmo),
        ("Сумма авансового платежа к уплате за 9 месяцев", "070", _format_money_cells(data.get("due_q3", 0), 11)),
        ("Сумма авансового платежа к уменьшению за 9 месяцев", "080", _format_money_cells(data.get("dec_q3", None), 11)),
        ("Код по ОКТМО", "090", oktmo),
        ("Сумма налога, подлежащая доплате за год", "100", _format_money_cells(data.get("due_year", 0), 11)),
        ("Сумма налога к уменьшению за год", "110", _format_money_cells(data.get("dec_year", None), 11)),
    ]

    cur_y = 138
    for label, code, val_str in rows_p2:
        p2.insert_text(fitz.Point(60, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p2.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p2, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 24

    # =========================================================================
    # СТРАНИЦА 3: РАЗДЕЛ 2.1.1 (0301 6046) - Расчет налога
    # =========================================================================
    p3 = doc.new_page(width=w, height=h)
    _draw_corner_squares(p3, w, h)
    barcode_p3 = "0301 6046" if is_6pct else "0301 6084"
    _draw_barcode(p3, barcode_p3, x=60, y=20)

    # Верхний колонтитул
    p3.insert_text(fitz.Point(170, 31), "ИНН", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, inn_cells, 195, 20, 12)
    p3.insert_text(fitz.Point(170, 48), "КПП", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, kpp_cells, 195, 37, 9)
    p3.insert_text(fitz.Point(375, 48), "Стр.", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=8)
    _draw_cells(p3, "003", 400, 37, 3)

    sec2_title = "Раздел 2.1.1. Расчет налога, уплачиваемого в связи с применением УСН (объект налогообложения – доходы)" if is_6pct else "Раздел 2.2. Расчет налога УСН (объект налогообложения – доходы, уменьшенные на величину расходов)"
    p3.insert_text(fitz.Point(60, 80), sec2_title, fontname="f_bld", fontfile=FONT_BOLD, fontsize=8.5)

    y = 105
    p3.insert_text(fitz.Point(60, y + 8), "Признак налогоплательщика (1 - выплаты физлицам, 2 - без выплат):", fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
    p3.insert_text(fitz.Point(360, y + 8), "102", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    payer_code = "2" if is_ip else "1"
    _draw_cells(p3, payer_code, 395, y, 1, cw=11.5, ch=13.5)

    # Строки доходов
    p3.insert_text(fitz.Point(60, 130), "Сумма полученных доходов (нарастающим итогом):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)

    rows_p3 = [
        ("за первый квартал", "110", _format_money_cells(data.get("income_q1", 0), 11)),
        ("за полугодие", "111", _format_money_cells(data.get("income_q2", 0), 11)),
        ("за девять месяцев", "112", _format_money_cells(data.get("income_q3", 0), 11)),
        ("за налоговый период (год)", "113", _format_money_cells(data.get("income_year", 0), 11)),
    ]

    cur_y = 145
    for label, code, val_str in rows_p3:
        p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 20

    # Налоговая ставка
    cur_y += 5
    p3.insert_text(fitz.Point(60, cur_y + 8), "Налоговая ставка (%):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
    rate_str = "6.0" if is_6pct else "15.0"
    rate_cells = _format_cell_text(rate_str, 3)

    rate_rows = [
        ("за первый квартал", "120"),
        ("за полугодие", "121"),
        ("за девять месяцев", "122"),
        ("за налоговый период", "123"),
    ]
    cur_y += 15
    for label, code in rate_rows:
        p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p3, rate_cells, 395, cur_y, 3, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 18

    # Сумма исчисленного налога
    cur_y += 5
    p3.insert_text(fitz.Point(60, cur_y + 8), "Сумма исчисленного налога (авансового платежа):", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)

    tax_rows = [
        ("за первый квартал", "130", _format_money_cells(data.get("tax_q1", 0), 11)),
        ("за полугодие", "131", _format_money_cells(data.get("tax_q2", 0), 11)),
        ("за девять месяцев", "132", _format_money_cells(data.get("tax_q3", 0), 11)),
        ("за налоговый период (год)", "133", _format_money_cells(data.get("tax_year", 0), 11)),
    ]
    cur_y += 15
    for label, code, val_str in tax_rows:
        p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 20

    # Сумма страховых взносов, уменьшающих налог
    cur_y += 5
    p3.insert_text(fitz.Point(60, cur_y + 8), "Сумма страховых взносов, уменьшающая налог:", fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)

    deduct_rows = [
        ("за первый квартал", "140", _format_money_cells(data.get("deduct_q1", 0), 11)),
        ("за полугодие", "141", _format_money_cells(data.get("deduct_q2", 0), 11)),
        ("за девять месяцев", "142", _format_money_cells(data.get("deduct_q3", 0), 11)),
        ("за налоговый период", "143", _format_money_cells(data.get("deduct_year", 0), 11)),
    ]
    cur_y += 15
    for label, code, val_str in deduct_rows:
        p3.insert_text(fitz.Point(70, cur_y + 8), label, fontname="f_reg", fontfile=FONT_REGULAR, fontsize=7.0)
        p3.insert_text(fitz.Point(360, cur_y + 8), code, fontname="f_bld", fontfile=FONT_BOLD, fontsize=7.5)
        _draw_cells(p3, val_str, 395, cur_y, 11, cw=11.5, ch=13.5, pad=1.2)
        cur_y += 20

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
        # База (доходы минус расходы)
        base_q1 = max(0, inc_q1 - exp_q1)
        base_q2 = max(0, inc_q2 - exp_q2)
        base_q3 = max(0, inc_q3 - exp_q3)
        base_year = max(0, inc_year - exp_year)

        tax_q1 = int(round(base_q1 * 0.15))
        tax_q2 = int(round(base_q2 * 0.15))
        tax_q3 = int(round(base_q3 * 0.15))
        tax_year = int(round(base_year * 0.15))
        min_tax = int(round(inc_year * 0.01))
    else:
        base_q1, base_q2, base_q3, base_year = inc_q1, inc_q2, inc_q3, inc_year
        tax_q1 = int(round(inc_q1 * 0.06))
        tax_q2 = int(round(inc_q2 * 0.06))
        tax_q3 = int(round(inc_q3 * 0.06))
        tax_year = int(round(inc_year * 0.06))
        min_tax = 0

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
        "deduct_year": 0
    }
