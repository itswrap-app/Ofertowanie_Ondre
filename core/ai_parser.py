"""Analiza zapytania klienta przez Claude API: jednorazowa + tryb czatu."""
import json
import re

MODEL = "claude-sonnet-4-6"

SYSTEM = """Jesteś asystentem ofertowym firmy ONDRE (drukarnia wielkoformatowa, oznakowanie, reklama).
Analizujesz zapytanie klienta i mapujesz je na pozycje z cennika. Zwracasz WYŁĄCZNIE poprawny JSON:
{"pozycje":[{"id_produktu":"P010"|null,"opis_pozycji":"...","ilosc_szt":liczba,
 "szerokosc_m":liczba|null,"wysokosc_m":liczba|null,"uwagi":"...","pewnosc":0-1}],
 "termin_realizacji":...|null,"dodatkowe_informacje":...|null,
 "dane_klienta":{"firma":...,"osoba":...,"email":...}}
Zasady: wymiary w metrach; warianty druku 4+0/4+4/5+0; produkt spoza cennika id_produktu=null;
nie zmyślaj ilości/wymiarów."""


def catalog_block(df) -> str:
    lines = []
    for _, r in df.iterrows():
        price = "IND" if r.get("base_cost") in (None, 0) or str(r.get("base_cost")) == "nan" else "OK"
        lines.append(f"{r['id']} | {r['section']} | {r['name']} | {r['variant'] or '-'} | cena:{price}")
    return "\n".join(lines)


def _parse_offer_json(text: str) -> dict:
    """Odporne wyciąganie JSON z odpowiedzi modelu."""
    t = (text or "").strip()
    t = re.sub(r"^```(json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        try:
            return json.loads(t[i:j + 1])
        except Exception:
            pass
    raise ValueError("Model nie zwrócił poprawnego JSON. Spróbuj ponownie lub przeformułuj.")


def analyze_email(email_text: str, products_df, api_key: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    user_msg = ("CENNIK (id | sekcja | nazwa | wariant | dostępność ceny):\n"
                + catalog_block(products_df) + "\n\n---\nZAPYTANIE KLIENTA:\n" + email_text.strip())
    resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM,
                                  messages=[{"role": "user", "content": user_msg}])
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = _parse_offer_json(text)
    data.setdefault("pozycje", [])
    return data


SYSTEM_CHAT = """Jesteś asystentem ofertowym firmy ONDRE (druk wielkoformatowy, oznakowanie, reklama).
Prowadzisz rozmowę z handlowcem i na bieżąco budujesz oraz korygujesz pozycje oferty.

Handlowiec może Cię poprawiać, np.: „D-Bond przyjmij z laminatem”, „lakierowanie = laminowanie”,
„połącz te dwie pozycje”, „dodaj montaż”, a także PODAWAĆ CENY, np. „150 zł za całość”,
„po 50 zł za sztukę”, „120 za metr”. ZAWSZE uwzględniaj te wskazówki w kolejnej propozycji.

Po KAŻDEJ wiadomości odpowiadasz WYŁĄCZNIE czystym, poprawnym JSON — bez żadnego tekstu przed
ani po, bez znaczników ```:
{
 "wiadomosc": "krótka odpowiedź do handlowca: przyjęte założenia i pytania o braki",
 "pozycje": [
   {
     "id_produktu": "P010" lub null,
     "opis_pozycji": "opis pozycji dla klienta",
     "ilosc_szt": liczba,
     "szerokosc_m": liczba|null, "wysokosc_m": liczba|null,
     "cena_szt": liczba|null,      // cena NETTO za sztukę, jeśli handlowiec ją podał/ustalił
     "cena_calosc": liczba|null,   // cena NETTO łączna za CAŁĄ pozycję, jeśli podano „za całość”
     "cena_m2": liczba|null,       // cena NETTO za m², jeśli podano
     "uwagi": "założenia/wątpliwości"|"",
     "pewnosc": 0-1
   }
 ],
 "termin_realizacji": tekst|null, "dodatkowe_informacje": tekst|null,
 "dane_klienta": {"firma":...|null,"osoba":...|null,"email":...|null,"telefon":...|null,"adres":...|null,"nip":...|null}
}

Zasady:
- "pozycje" to ZAWSZE pełna, aktualna lista (nie różnice).
- CENY: gdy handlowiec poda cenę, wpisz ją w odpowiednie pole pozycji (cena_calosc / cena_szt / cena_m2),
  aby trafiła do tabeli. Gdy ceny NIE podał — zostaw te pola null (aplikacja policzy z cennika).
  Nigdy nie wstawiaj cen „z głowy”.
- Wymiary w metrach. Warianty druku: 4+0 jednostronny kolor, 4+4 dwustronny,
  5+0/5+5 z kolorem dodatkowym; gdy klient nie precyzuje — przyjmij 4+0 i odnotuj w uwagach.
- Produkt spoza cennika: id_produktu=null, pewnosc=0.
- "dane_klienta": wyciągnij ze stopki maila co się da (firma, osoba, email, telefon, adres, NIP).
- Nie wymyślaj ilości/wymiarów — gdy brak, zostaw null i dopytaj w "wiadomosc".
"""


def chat_offer(api_messages: list, api_key: str):
    """api_messages: pełna historia [{role, content}]. Zwraca (dict, raw_text)."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM_CHAT,
                                  messages=api_messages)
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = _parse_offer_json(text)
    data.setdefault("pozycje", [])
    data.setdefault("wiadomosc", "")
    return data, text
