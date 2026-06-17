"""Użytkownicy — zarządzanie kontami (tylko admin)."""
import streamlit as st

from core import auth, db
from core.ui import page_setup

page_setup("Użytkownicy", "👥")
me = auth.login_gate()
auth.require_admin()

st.title("👥 Użytkownicy")
st.caption("Konta handlowców i administratorów. Każdy loguje się własnym e-mailem; "
           "jego dane wchodzą na ofertę jako osoba kontaktowa.")

dfu = db.users_df()
st.dataframe(
    dfu.rename(columns={"email": "E-mail", "name": "Imię i nazwisko", "phone": "Telefon",
                        "role": "Rola", "active": "Aktywny", "created_ts": "Utworzono"}),
    width="stretch", hide_index=True, column_config={"id": None})

st.divider()
st.subheader("➕ Dodaj użytkownika")
with st.form("add_user"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Imię i nazwisko *")
    email = c2.text_input("E-mail (login) *")
    phone = c1.text_input("Telefon")
    role = c2.selectbox("Rola", auth.ROLES, index=1)
    p1 = c1.text_input("Hasło startowe *", type="password")
    p2 = c2.text_input("Powtórz hasło *", type="password")
    submitted = st.form_submit_button("Utwórz konto", type="primary")
if submitted:
    if not (name.strip() and email.strip() and p1):
        st.error("Uzupełnij imię, e-mail i hasło.")
    elif db.get_user_by_email(email):
        st.error("Konto o tym e-mailu już istnieje.")
    elif p1 != p2:
        st.error("Hasła nie są identyczne.")
    elif len(p1) < 8:
        st.error("Hasło powinno mieć min. 8 znaków.")
    else:
        db.create_user(email, name, phone, auth.hash_pw(p1), role=role)
        st.success("Utworzono konto dla %s. Przekaż hasło startowe — użytkownik zmieni je w „Mój profil”." % name)
        st.rerun()

st.divider()
st.subheader("✏️ Edytuj konto")
if dfu.empty:
    st.stop()
opts = {"%s — %s (%s)" % (r["name"], r["email"], r["role"]): int(r["id"])
        for _, r in dfu.iterrows()}
pick = st.selectbox("Konto", list(opts.keys()))
uid = opts[pick]
target = db.get_user(uid)

c1, c2, c3 = st.columns(3)
new_role = c1.selectbox("Rola", auth.ROLES, index=auth.ROLES.index(target["role"]))
new_active = c2.selectbox("Status", ["aktywny", "nieaktywny"],
                          index=0 if target["active"] else 1)
if c3.button("💾 Zapisz zmiany"):
    if uid == me["id"] and (new_role != "admin" or new_active != "aktywny"):
        st.error("Nie możesz odebrać uprawnień ani dezaktywować własnego konta.")
    else:
        db.update_user(uid, role=new_role, active=1 if new_active == "aktywny" else 0)
        st.success("Zaktualizowano konto.")
        st.rerun()

with st.expander("🔑 Resetuj hasło użytkownika"):
    with st.form("reset_pw"):
        np1 = st.text_input("Nowe hasło", type="password")
        np2 = st.text_input("Powtórz", type="password")
        if st.form_submit_button("Ustaw nowe hasło"):
            if np1 != np2:
                st.error("Hasła nie są identyczne.")
            elif len(np1) < 8:
                st.error("Hasło powinno mieć min. 8 znaków.")
            else:
                db.update_user(uid, password_hash=auth.hash_pw(np1))
                st.success("Hasło zresetowane. Przekaż je użytkownikowi.")
