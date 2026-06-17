"""Logika cenowa: cena = koszt bazowy * (1 + narzut poziomu)."""
import math
from .db import TIER_COL


def unit_price(base_cost, markup):
    if base_cost in (None, 0) or markup is None:
        return None
    try:
        b, m = float(base_cost), float(markup)
        if math.isnan(b) or math.isnan(m) or b == 0:
            return None
        return round(b * (1 + m), 2)
    except (TypeError, ValueError):
        return None


def price_for(product_row, tier_name):
    """product_row: wiersz z products_df (Series/dict)."""
    col = TIER_COL.get(tier_name)
    if not col:
        return None
    return unit_price(product_row.get("base_cost"), product_row.get(col))


def compute_item(item: dict) -> dict:
    """Uzupełnia powierzchnię i wartość pozycji oferty.

    item: ilosc, szer, wys, cena, rabat (%); unit produktu w item['unit'].
    """
    qty = float(item.get("ilosc") or 0)
    szer = item.get("szer")
    wys = item.get("wys")
    cena = item.get("cena")
    rabat = float(item.get("rabat") or 0)
    unit = item.get("unit") or "m2"

    area = None
    if unit == "m2" and szer and wys:
        area = round(float(szer) * float(wys) * qty, 3)
    item["pow"] = area

    if cena in (None, ""):
        item["wartosc"] = None
    else:
        base = (area if area is not None else qty) * float(cena)
        item["wartosc"] = round(base * (1 - rabat / 100.0), 2)
    return item


def totals(items: list[dict], vat_rate: float):
    net = sum(i["wartosc"] for i in items if i.get("wartosc") and not math.isnan(i["wartosc"]))
    vat = round(net * vat_rate / 100.0, 2)
    return round(net, 2), vat, round(net + vat, 2)
