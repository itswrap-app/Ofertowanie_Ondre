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
        var = r["variant"] if isinstance(r.get("variant"), str) and r["variant"].strip() else "-"
        lines.append(f"{r['id']} | {r['section']} | {r['name']} | {var} | cena:{price}")
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
     "grupa": tekst|null,          // etykieta zestawu, np. „Oklejenie witryn" — pozycje z tą samą
                                    // grupą aplikacja połączy w JEDEN wiersz i zsumuje
     "rola": "folia"|"laminat"|"montaz"|null,  // rola w zestawie (do policzenia montażu)
     "uwagi": "założenia/wątpliwości"|"",
     "pewnosc": 0-1
   }
 ],
 "termin_realizacji": tekst|null, "dodatkowe_informacje": tekst|null,
 "dane_klienta": {"firma":...|null,"osoba":...|null,"email":...|null,"telefon":...|null,"adres":...|null,"nip":...|null}
}

Zasady:
- "pozycje" to ZAWSZE pełna, aktualna lista (nie różnice).
- Cennik podaje JEDNOSTKĘ i CENĘ za jednostkę dla poziomu klienta (do orientacji).
- ZWYKŁE pojedyncze pozycje z cennika: NIE wpisuj cen — zostaw cena_szt/cena_calosc/cena_m2 = null,
  aplikacja policzy z cennika. Ceny wpisuj TYLKO gdy handlowiec sam podał cenę. Nie licz „z głowy”.
- MATERIAŁY OD m² podane jako łączny metraż BEZ wymiarów (np. „8 m²"): wpisz metraż w ilosc_szt,
  a szerokosc_m/wysokosc_m zostaw null (aplikacja pomnoży cena/m² × metraż).
- POZYCJE ZŁOŻONE (np. oklejenie witryn = folia + laminat + montaż): zwróć składniki jako OSOBNE
  pozycje, każda z TĄ SAMĄ wartością "grupa" (np. „Oklejenie witryn 8 m²") i właściwą "rola"
  ("folia"/"laminat"/"montaz"). Montaż: osobna pozycja rola="montaz", BEZ ceny i bez ilości/wymiarów.
  NIE licz sam montażu ani sumy — aplikacja policzy montaż = 2× wartość folii i połączy grupę
  w jeden wiersz. Rozbijaj (bez grupy) tylko gdy handlowiec wyraźnie poprosi („rozbij osobno").
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
