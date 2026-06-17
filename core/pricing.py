"""Logika cenowa ONDRE.

Cennik:  cena/m² = koszt bazowy * (1 + narzut poziomu).
Pozycja oferty rozróżnia:
  • cena/m²  — cena jednostkowa za metr kwadratowy (gdy pozycja liczona od powierzchni),
  • cena/szt — cena za jedną sztukę (= cena/m² * powierzchnia 1 szt, lub wpisana wprost
               dla pozycji liczonych od sztuki),
  • wartość  = cena/szt * ilość * (1 - rabat).
Obsługuje minimalną cenę za sztukę (min_price) z cennika.
"""
import math


def _f(v):
    """Bezpieczna konwersja na float (None/'' / NaN -> None)."""
    if v in (None, ""):
        return None
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def unit_price(base_cost, markup):
    b, m = _f(base_cost), _f(markup)
    if b in (None, 0) or m is None:
        return None
    return round(b * (1 + m), 2)


def price_for(product_row, tier_name):
    from .db import TIER_COL
    col = TIER_COL.get(tier_name)
    if not col:
        return None
    return unit_price(product_row.get("base_cost"), product_row.get(col))


def compute_line(qty, szer, wys, cena_m2, cena_szt, rabat,
                 min_price=None, driver=None):
    """Przelicza jedną pozycję. driver = 'm2' | 'szt' | None (auto).

    Zwraca dict: cena_m2, cena_szt, pow (łączna), wartosc.
    """
    qty = _f(qty) or 0
    szer, wys = _f(szer), _f(wys)
    cena_m2, cena_szt = _f(cena_m2), _f(cena_szt)
    rabat = _f(rabat) or 0
    min_price = _f(min_price)

    area = round(szer * wys, 4) if (szer and wys) else None      # powierzchnia 1 szt
    pow_total = round(area * qty, 3) if (area and qty) else None

    # ustal cenę za sztukę / m² wg tego, co użytkownik zmienił
    if driver == "m2" and area and cena_m2 is not None:
        cena_szt = round(cena_m2 * area, 2)
    elif driver == "szt" and area and cena_szt is not None:
        cena_m2 = round(cena_szt / area, 2)
    else:
        if area and cena_m2 is not None:
            cena_szt = round(cena_m2 * area, 2)
        elif not area and cena_m2 is not None and cena_szt is None:
            cena_szt = cena_m2  # cena/m² bez wymiarów traktujemy jak za sztukę

    # minimalna cena za sztukę
    if min_price and cena_szt is not None and cena_szt < min_price:
        cena_szt = round(min_price, 2)
        if area:
            cena_m2 = round(cena_szt / area, 2)

    wartosc = (round(cena_szt * qty * (1 - rabat / 100.0), 2)
               if (cena_szt is not None and qty) else None)
    return {"cena_m2": cena_m2, "cena_szt": cena_szt,
            "pow": pow_total, "wartosc": wartosc}


def compute_item(item: dict) -> dict:
    """Wariant dla gotowego słownika pozycji (PDF/seed/test)."""
    res = compute_line(item.get("ilosc"), item.get("szer"), item.get("wys"),
                       item.get("cena_m2", item.get("cena")),
                       item.get("cena_szt"), item.get("rabat"),
                       item.get("min_price"), item.get("driver"))
    item.update(res)
    return item


def totals(items, vat_rate: float):
    net = sum(i["wartosc"] for i in items
              if i.get("wartosc") not in (None, "") and not math.isnan(i["wartosc"]))
    vat = round(net * vat_rate / 100.0, 2)
    return round(net, 2), vat, round(net + vat, 2)
