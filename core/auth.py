"""Uwierzytelnianie i konta użytkowników (bcrypt + tabela users)."""
import bcrypt
import streamlit as st

from core import db

ROLES = ["admin", "handlowiec"]


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_pw(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        return False


def current_user():
    return st.session_state.get("user")


def is_admin() -> bool:
    u = current_user()
    return bool(u and u.get("role") == "admin")


def logout():
    st.session_state.pop("user", None)


def _first_run_setup():
    st.title("🚀 Pierwsze uruchomienie")
    st.write("Nie ma jeszcze żadnych kont. Utwórz konto **administratora** "
             "(zarządza cennikiem, ustawieniami i użytkownikami).")
    with st.form("setup_admin"):
        name = st.text_input("Imię i nazwisko")
        email = st.text_input("E-mail (login)")
        phone = st.text_input("Telefon (opcjonalnie)")
        p1 = st.text_input("Hasło", type="password")
        p2 = st.text_input("Powtórz hasło", type="password")
        ok = st.form_submit_button("Utwórz konto administratora", type="primary")
    if ok:
        if not (name.strip() and email.strip() and p1):
            st.error("Uzupełnij imię, e-mail i hasło.")
        elif p1 != p2:
            st.error("Hasła nie są identyczne.")
        elif len(p1) < 8:
            st.error("Hasło powinno mieć min. 8 znaków.")
        else:
            db.create_user(email, name, phone, hash_pw(p1), role="admin")
            st.success("Konto utworzone. Zaloguj się poniżej.")
            st.rerun()
    st.stop()


def _login_form():
    st.title("🔐 Logowanie")
    st.caption("ONDRE · generator ofert")
    with st.form("login"):
        email = st.text_input("E-mail")
        pw = st.text_input("Hasło", type="password")
        ok = st.form_submit_button("Zaloguj", type="primary")
    if ok:
        u = db.get_user_by_email(email)
        if not u or not u.get("active"):
            st.error("Nie znaleziono aktywnego konta o tym adresie.")
        elif not check_pw(pw, u.get("password_hash") or ""):
            st.error("Błędne hasło.")
        else:
            st.session_state["user"] = {
                "id": u["id"], "email": u["email"], "name": u["name"],
                "phone": u.get("phone") or "", "role": u["role"]}
            st.rerun()
    st.stop()


def _bootstrap_from_secrets():
    """Jeśli baza pusta a w sekretach są BOOTSTRAP_ADMIN_*, zakłada konto admina
    automatycznie (zero ekranów konfiguracyjnych po wdrożeniu)."""
    if db.count_users() > 0:
        return
    email = db._secret("BOOTSTRAP_ADMIN_EMAIL").strip()
    pw = db._secret("BOOTSTRAP_ADMIN_PASSWORD")
    name = db._secret("BOOTSTRAP_ADMIN_NAME", "Administrator").strip()
    if email and pw:
        db.create_user(email, name, "", hash_pw(pw), role="admin")


def login_gate():
    """Wstaw na początku każdej strony. Zwraca słownik zalogowanego użytkownika."""
    db.seed_if_empty()
    if current_user():
        _sidebar_user()
        return current_user()
    _bootstrap_from_secrets()
    if db.count_users() == 0:
        _first_run_setup()
    _login_form()


def require_admin():
    """Na stronach tylko dla admina. Zatrzymuje renderowanie dla handlowca."""
    if not is_admin():
        st.error("Ta sekcja jest dostępna tylko dla administratora.")
        st.stop()


def _sidebar_user():
    u = current_user()
    with st.sidebar:
        st.markdown("**👤 %s**" % u["name"])
        st.caption("%s · %s" % (u["email"], u["role"]))
        if st.button("Wyloguj", width="stretch"):
            logout()
            st.rerun()
