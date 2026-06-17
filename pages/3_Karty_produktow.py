"""Karty produktowe — przypisywanie PDF do pozycji cennika."""
import streamlit as st

from core import auth, db
from core.ui import page_setup

page_setup("Karty produktowe", "📎")
auth.login_gate()
auth.require_admin()
st.title("📎 Karty produktowe")

st.caption("Karta (PDF) przypisana do produktu jest automatycznie doklejana "
           "do oferty, gdy produkt znajdzie się w tabeli pozycji.")

prod = db.products_df(active_only=True)
prod["label"] = (prod["id"] + " · " + prod["name"] + " "
                 + prod["variant"].fillna("")).str.strip()

pick = st.selectbox("Produkt", prod["label"])
row = prod[prod["label"] == pick].iloc[0]

cur = row["card_file"]
card_bytes = db.get_card_bytes(row["id"])
if isinstance(cur, str) and cur and card_bytes:
    st.success("Aktualna karta: **%s**" % cur)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Pobierz kartę", card_bytes, file_name=cur)
    if c2.button("🗑 Usuń przypisanie"):
        db.remove_card(row["id"])
        st.rerun()
else:
    st.info("Brak karty dla tego produktu.")

up = st.file_uploader("Wgraj kartę PDF", type=["pdf"], key="card_up")
if up and st.button("💾 Zapisz kartę", type="primary"):
    fname = "%s.pdf" % row["id"]
    db.set_card(row["id"], fname, up.getvalue(),
                user=auth.current_user()["name"])
    st.success("Zapisano kartę dla %s." % row["id"])
    st.rerun()

st.divider()
st.subheader("Produkty z kartami")
have = prod[prod["card_file"].notna()][["id", "name", "variant", "card_file"]]
if have.empty:
    st.info("Żaden produkt nie ma jeszcze karty.")
else:
    st.dataframe(have, width="stretch", hide_index=True)
