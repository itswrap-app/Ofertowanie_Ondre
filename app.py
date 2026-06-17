"""ONDRE Oferty — panel główny."""
import streamlit as st

from core import auth, db
from core.ui import get_secret, page_setup

page_setup("Start", "🏠")
user = auth.login_gate()

st.title("Generator ofert ONDRE")
st.caption("Witaj, %s! Mail klienta → analiza AI → tabela pozycji → PDF z kartami produktów."
           % user["name"].split(" ")[0])

df = db.products_df()
active = df[df["active"] == 1]
missing = active["base_cost"].isna().sum()
my_offers = db.offers_df(1000, user_id=user["id"], is_admin=auth.is_admin())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Pozycje w cenniku", len(active))
c2.metric("Do wyceny indywidualnej", int(missing))
c3.metric("Karty produktowe", int(active["card_file"].notna().sum()))
c4.metric("Oferty (wszystkie)" if auth.is_admin() else "Twoje oferty", len(my_offers))

st.divider()
left, right = st.columns([1, 1])

with left:
    st.subheader("Szybki start")
    st.page_link("pages/1_Nowa_oferta.py", label="➕ Nowa oferta", icon="🧾")
    st.page_link("pages/4_Ustawienia.py", label="🔧 Mój profil i ustawienia", icon="👤")
    if auth.is_admin():
        st.page_link("pages/2_Cennik_admin.py", label="🗂️ Cennik (admin)", icon="🗂️")
        st.page_link("pages/3_Karty_produktow.py", label="📎 Karty produktowe", icon="📄")
        st.page_link("pages/5_Uzytkownicy.py", label="👥 Użytkownicy", icon="👥")

    st.subheader("Status integracji")
    ok_ai = bool(get_secret("ANTHROPIC_API_KEY"))
    ok_pd = bool(get_secret("PIPEDRIVE_API_TOKEN"))
    ok_db = bool(get_secret("DATABASE_URL"))
    st.write(("✅" if ok_ai else "⚠️") + " Claude API (analiza maili)")
    st.write(("✅" if ok_pd else "⚠️") + " Pipedrive")
    st.write(("✅ Postgres (dane trwałe)" if ok_db
              else "⚠️ Lokalny SQLite — ustaw DATABASE_URL na produkcji"))

with right:
    st.subheader("Wszystkie oferty" if auth.is_admin() else "Twoje ostatnie oferty")
    recent = db.offers_df(15, user_id=user["id"], is_admin=auth.is_admin())
    if recent.empty:
        st.info("Brak ofert — utwórz pierwszą w „Nowa oferta”.")
    else:
        cols = {"number": "Numer", "ts": "Data", "client_name": "Klient",
                "tier": "Poziom", "total_net": "Netto [zł]", "user_name": "Handlowiec"}
        view = recent.rename(columns=cols)
        drop = ["id", "pdf_name"] + ([] if auth.is_admin() else ["Handlowiec"])
        st.dataframe(view.drop(columns=[c for c in drop if c in view.columns]),
                     width="stretch", hide_index=True)
