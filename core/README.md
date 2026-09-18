# ONDRE Oferty 🧾

Wieloużytkownikowy generator ofert dla BOK i handlowców ONDRE:
**logowanie → mail klienta → analiza AI (Claude) → tabela pozycji z cennika →
PDF w identyfikacji ONDRE → karty produktowe → Pipedrive.**

## Funkcje

- **Konta i role** — każdy handlowiec ma własny login; jego dane wchodzą na ofertę jako
  osoba kontaktowa. Role: **admin** (cennik, ustawienia firmy, użytkownicy, wszystkie oferty)
  i **handlowiec** (tworzy oferty, widzi swoje). Hasła hashowane (bcrypt).
- **Trwała baza** — SQLAlchemy: lokalnie SQLite, na produkcji **Postgres** (Supabase/Neon).
  Cennik, oferty (z PDF) i karty produktowe są w bazie — przeżywają redeploy.
- **Cennik w bazie** — edycja w panelu admina, `cena = koszt bazowy × (1 + narzut)`,
  5 poziomów (Katalogowa/Klient stały/Pośrednik/Agencyjny/Jedi), historia zmian, import/eksport XLSX.
- **Analiza zapytania AI** — Claude czyta mail, wyciąga pozycje/ilości/wymiary (w metrach),
  mapuje na cennik, zaznacza wątpliwości; pozycje spoza cennika → „do wyceny”.
- **Edytowalna tabela pozycji**, rabaty, uzupełnianie/nadpisywanie cen z cennika.
- **PDF w CI ONDRE** — gradientowa belka, logo w kontrze, tabela z tintami niebieskiego,
  netto/VAT/brutto, stopka z danymi spółki, numeracja stron; karty produktowe doklejane na końcu.
- **Pipedrive** — wyszukiwanie firm, deale, pobieranie maili, wysyłka PDF do deala.

## Role i pierwsze logowanie

Przy pierwszym uruchomieniu (pusta baza) aplikacja poprosi o **utworzenie konta administratora**.
Kolejne konta admin zakłada w zakładce **Użytkownicy** i przekazuje hasła startowe —
użytkownik zmienia hasło w „Mój profil”.

## Szybki start (lokalnie)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # uzupełnij klucze
streamlit run app.py
```

Bez `DATABASE_URL` używany jest lokalny SQLite (`data/ondre.db`) — wygodny do testów,
ale **na produkcji ustaw Postgres**, inaczej dane znikną przy redeployu.

## Sekrety (`.streamlit/secrets.toml`)

| Klucz | Do czego |
|---|---|
| `DATABASE_URL` | trwała baza Postgres: `postgresql://user:pass@host:5432/db` |
| `ANTHROPIC_API_KEY` | analiza maili przez Claude |
| `PIPEDRIVE_API_TOKEN` | Pipedrive (klienci, deale, maile, wysyłka PDF) |

## Wdrożenie produkcyjne

### 1. Baza Postgres (Supabase — darmowy plan)
1. supabase.com → New project (zapisz hasło do bazy).
2. Project Settings → Database → **Connection string → URI**.
3. Skopiuj URI (`postgresql://postgres:...@...supabase.com:5432/postgres`) → to `DATABASE_URL`.
   (Alternatywa: neon.tech — też darmowy Postgres.)

### 2. GitHub
Repozytorium **prywatne** (w środku są narzuty cenowe). `secrets.toml` i `data/` są w `.gitignore`.

### 3. Streamlit Community Cloud
1. share.streamlit.io → New app → wskaż repo i `app.py`.
2. **App settings → Secrets** → wklej zawartość `secrets.toml` (z `DATABASE_URL`).
3. Deploy. Pierwszy ekran utworzy konto admina.

## Czcionka Apertura

PDF używa fallbacku DejaVu Sans (pełne polskie znaki). Po wgraniu
`Apertura-Regular.ttf` i `Apertura-Bold.ttf` do `assets/fonts/` zostaną wykryte automatycznie.

## Struktura

```
app.py                    # logowanie + dashboard
pages/1_Nowa_oferta.py    # workflow oferty (handlowiec)
pages/2_Cennik_admin.py   # cennik (admin)
pages/3_Karty_produktow.py# karty PDF (admin)
pages/4_Ustawienia.py     # mój profil (każdy) + firma/integracje (admin)
pages/5_Uzytkownicy.py    # zarządzanie kontami (admin)
core/db.py                # SQLAlchemy: SQLite/Postgres, cennik, oferty, karty, users
core/auth.py              # logowanie, role, bcrypt
core/pricing.py           # silnik cenowy
core/ai_parser.py         # Claude API → pozycje
core/pdf_offer.py         # PDF w CI ONDRE + merge kart
core/pipedrive.py         # klient API Pipedrive
assets/branding|fonts|seed/
```

## Roadmapa

- [ ] Logowanie Google (OIDC) zamiast haseł
- [ ] Auto-poziom cenowy z pola w Pipedrive
- [ ] Webhook Pipedrive: nowy mail → szkic oferty
- [ ] Wersjonowanie ofert i statusy (wysłana/zaakceptowana)
- [ ] Minimalna powierzchnia rozliczeniowa / dopłaty z arkusza „Obróbka”
