"""Analiza zapytania klienta (mail) przez Claude API → pozycje oferty."""
import json
import re

MODEL = "claude-sonnet-4-6"

SYSTEM = """Jesteś asystentem ofertowym firmy ONDRE (drukarnia wielkoformatowa, oznakowanie, reklama).
Analizujesz zapytanie klienta (treść maila) i mapujesz je na pozycje z cennika firmy.

Zwracasz WYŁĄCZNIE poprawny JSON (bez markdown, bez komentarzy) o strukturze:
{
 "pozycje": [
   {
     "id_produktu": "P010" lub null (gdy brak dopasowania w cenniku),
     "opis_pozycji": "krótki opis pozycji językiem zrozumiałym dla klienta",
     "ilosc_szt": liczba (domyślnie 1),
     "szerokosc_m": liczba w metrach lub null,
     "wysokosc_m": liczba w metrach lub null,
     "uwagi": "wątpliwości, brakujące informacje, założenia" lub "",
     "pewnosc": liczba 0-1 (pewność dopasowania do cennika)
   }
 ],
 "termin_realizacji": "termin z maila" lub null,
 "dodatkowe_informacje": "montaż, dostawa, projekt itp." lub null,
 "dane_klienta": {"firma": ... lub null, "osoba": ... lub null, "email": ... lub null}
}

Zasady:
- Wymiary ZAWSZE przeliczaj na metry (np. 50x70 cm → 0.5 i 0.7).
- Warianty druku: 4+0 = jednostronny kolor, 4+4 = dwustronny kolor, 1+0 = jednostronny mono,
  5+0 / 5+5 = z kolorem dodatkowym (np. białym). Gdy klient nie precyzuje, wybierz 4+0 i odnotuj w uwagach.
- Jeśli klient prosi o produkt spoza cennika, dodaj pozycję z id_produktu=null i pewnosc=0.
- Gdy w mailu jest kilka produktów/wymiarów, utwórz osobne pozycje.
- Nie wymyślaj ilości ani wymiarów — jeśli ich brak, zostaw null i opisz w uwagach.
"""


def catalog_block(df) -> str:
    lines = []
    for _, r in df.iterrows():
        price = "IND" if r.get("base_cost") in (None, 0) or str(r.get("base_cost")) == "nan" else "OK"
        lines.append(f"{r['id']} | {r['section']} | {r['name']} | {r['variant'] or '-'} | cena:{price}")
    return "\n".join(lines)


def analyze_email(email_text: str, products_df, api_key: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        "CENNIK (id | sekcja | nazwa | wariant druku | dostępność ceny):\n"
        + catalog_block(products_df)
        + "\n\n---\nZAPYTANIE KLIENTA:\n"
        + email_text.strip()
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    if "pozycje" not in data:
        raise ValueError("Brak klucza 'pozycje' w odpowiedzi AI")
    return data
