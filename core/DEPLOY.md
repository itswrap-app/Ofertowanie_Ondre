# Wdrożenie ONDRE Oferty — jedna ścieżka, ~10 minut

Wykonaj kroki po kolei. Nie ma wariantów do wyboru.

## Krok 1 · Baza danych (Supabase, darmowa)
1. Wejdź na **supabase.com** → zaloguj się (GitHub/Google) → **New project**.
2. Nazwa dowolna, ustaw i **zapisz** „Database Password”, region: Frankfurt (EU).
3. Po utworzeniu: **Project Settings → Database → Connection string → URI**.
4. Skopiuj URI. Wygląda tak:
   `postgresql://postgres:HASLO@db.xxxxx.supabase.co:5432/postgres`
   — to jest Twój `DATABASE_URL` (wstaw zapisane hasło w miejsce `HASLO`).

## Krok 2 · Repozytorium (GitHub, prywatne)
W terminalu, w rozpakowanym folderze projektu:
```bash
git init
git add .
git commit -m "ONDRE Oferty"
gh repo create ondre-oferty --private --source=. --push
# (lub: utwórz puste, prywatne repo na github.com i:)
# git remote add origin git@github.com:TWOJ_LOGIN/ondre-oferty.git
# git push -u origin main
```
`secrets.toml` i `data/` są w `.gitignore` — nie trafią do repo.

## Krok 3 · Hosting (Streamlit Community Cloud)
1. **share.streamlit.io** → zaloguj GitHubem → **New app** → **Deploy a public app from GitHub**
   (repo prywatne jest OK) → wskaż repo `ondre-oferty`, branch `main`, plik `app.py`.
2. **Advanced settings → Python 3.12**.
3. **Advanced settings → Secrets** → wklej (uzupełnij wartości):
   ```toml
   DATABASE_URL = "postgresql://postgres:HASLO@db.xxxxx.supabase.co:5432/postgres"
   ANTHROPIC_API_KEY = "twój-klucz"
   PIPEDRIVE_API_TOKEN = "twój-token"
   BOOTSTRAP_ADMIN_EMAIL = "borys@ondre.pl"
   BOOTSTRAP_ADMIN_PASSWORD = "mocne-haslo-startowe"
   BOOTSTRAP_ADMIN_NAME = "Borys"
   ```
4. **Deploy**. Po chwili masz publiczny link.

## Krok 4 · Pierwsze logowanie
- Wejdź na link → zaloguj się e-mailem i hasłem z `BOOTSTRAP_ADMIN_*`.
- **Użytkownicy** → dodaj handlowców (każdy dostaje hasło startowe, zmieni je w „Mój profil”).
- **Cennik** → uzupełnij 41 pozycji „do wyceny”, gdy będziecie gotowi.
- (Opcjonalnie) usuń `BOOTSTRAP_ADMIN_PASSWORD` z Secrets po pierwszym logowaniu.

## Aktualizacje
`git push` na `main` → Streamlit Cloud automatycznie przebuduje aplikację.
Dane (baza Postgres) zostają nienaruszone.
