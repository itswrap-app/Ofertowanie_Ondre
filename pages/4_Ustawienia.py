"""Mój profil + (dla admina) dane firmy, parametry oferty, integracje."""
import streamlit as st

from core import auth, db
from core.pipedrive import PipedriveClient
from core.ui import get_secret, page_setup

page_setup("Ustawienia", "🔧")
user = auth.login_gate()

st.title("🔧 Ustawienia")

# ---------------- MÓJ PROFIL (każdy użytkownik) ----------------
st.subheader("👤 Mój profil")
st.caption("Te dane trafiają na ofertę jako osoba kontaktowa.")
u = db.get_user(user["id"])
c1, c2 = st.columns(2)
p_name = c1.text_input("Imię i nazwisko", u["name"])
p_phone = c2.text_input("Telefon", u.get("phone") or "")
st.text_input("E-mail (login)", u["email"], disabled=True)
if st.button("💾 Zapisz profil"):
    db.update_user(user["id"], name=p_name.strip(), phone=p_phone.strip())
    st.session_state["user"]["name"] = p_name.strip()
    st.session_state["user"]["phone"] = p_phone.strip()
    st.success("Zapisano profil.")
    st.rerun()

with st.expander("🔑 Zmień hasło"):
    with st.form("change_pw"):
        old = st.text_input("Obecne hasło", type="password")
        n1 = st.text_input("Nowe hasło", type="password")
        n2 = st.text_input("Powtórz nowe hasło", type="password")
        if st.form_submit_button("Zmień hasło"):
            full = db.get_user(user["id"])
            if not auth.check_pw(old, full.get("password_hash") or ""):
                st.error("Obecne hasło jest błędne.")
            elif n1 != n2:
                st.error("Nowe hasła nie są identyczne.")
            elif len(n1) < 8:
                st.error("Hasło powinno mieć min. 8 znaków.")
            else:
                db.update_user(user["id"], password_hash=auth.hash_pw(n1))
                st.success("Hasło zmienione.")

# ---------------- DANE FIRMY + INTEGRACJE (admin) ----------------
if not auth.is_admin():
    st.info("Dane firmy, parametry oferty i integracje może zmieniać administrator.")
    st.stop()

st.divider()
s = db.get_settings()
st.subheader("🏢 Dane firmy (stopka i nagłówek oferty)")
st.caption("Wartości startowe z brandbooka ONDRE — zweryfikuj NIP/REGON/konto przed użyciem produkcyjnym.")
c1, c2 = st.columns(2)
s["company_name"] = c1.text_input("Nazwa", s["company_name"])
s["company_address"] = c2.text_input("Adres", s["company_address"])
s["company_nip"] = c1.text_input("NIP", s["company_nip"])
s["company_regon"] = c2.text_input("REGON", s["company_regon"])
s["company_email"] = c1.text_input("E-mail", s["company_email"])
s["company_phone"] = c2.text_input("Telefon", s["company_phone"])
s["company_web"] = c1.text_input("WWW", s["company_web"])
s["company_bank"] = c2.text_input("Nr konta", s["company_bank"])

st.subheader("📄 Parametry oferty")
c6, c7, c8 = st.columns(3)
s["offer_prefix"] = c6.text_input("Prefiks numeracji", s["offer_prefix"])
s["offer_validity_days"] = str(c7.number_input(
    "Ważność oferty [dni]", value=int(s["offer_validity_days"]), min_value=1))
s["vat_rate"] = str(c8.number_input("Stawka VAT [%]", value=float(s["vat_rate"]), step=1.0))
s["payment_terms"] = st.text_area("Warunki (drukowane na ofercie)", s["payment_terms"], height=80)

if st.button("💾 Zapisz ustawienia firmy", type="primary"):
    db.save_settings(s)
    st.success("Zapisano.")

st.divider()
st.subheader("🔌 Integracje (klucze w secrets)")
st.write(("✅" if get_secret("ANTHROPIC_API_KEY") else "⚠️")
         + " **ANTHROPIC_API_KEY** — analiza maili przez Claude")
st.write(("✅" if get_secret("DATABASE_URL") else "⚠️")
         + " **DATABASE_URL** — trwała baza Postgres (bez tego dane są ulotne!)")
tok = get_secret("PIPEDRIVE_API_TOKEN")
st.write(("✅" if tok else "⚠️") + " **PIPEDRIVE_API_TOKEN** — klienci, deale, maile, wysyłka PDF")
if tok and st.button("Testuj połączenie z Pipedrive"):
    try:
        name, company = PipedriveClient(tok).test()
        st.success("Połączono: %s (%s)" % (name, company))
    except Exception as e:
        st.error("Błąd: %s" % e)

st.caption("Czcionka oferty: wrzuć **Apertura-Regular.ttf** i **Apertura-Bold.ttf** "
           "do assets/fonts/, aby PDF był w 100% zgodny z CI (obecnie fallback: DejaVu).")
