"""Cennik — panel administratora."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core import auth, db, pricing
from core.ui import page_setup

page_setup("Cennik (admin)", "⚙️")
auth.login_gate()
auth.require_admin()
st.title("⚙️ Cennik — administracja")

df = db.products_df()

f1, f2, f3 = st.columns([2, 2, 1])
sections = sorted(x for x in df["section"].dropna().unique())
sel = f1.multiselect("Sekcja", sections)
search = f2.text_input("Szukaj w nazwie")
show_prices = f3.toggle("Podgląd cen", value=False,
                        help="Pokaż wyliczone ceny dla 5 poziomów (tylko podgląd).")

view = df.copy()
if sel:
    view = view[view["section"].isin(sel)]
if search.strip():
    view = view[view["name"].str.contains(search.strip(), case=False, na=False)]

if show_prices:
    for tname, tcol in db.TIERS:
        view["Cena: " + tname] = view.apply(
            lambda r: pricing.unit_price(r["base_cost"], r[tcol]), axis=1)

st.caption("Edytuj koszt bazowy i narzuty — ceny liczą się jako koszt × (1 + narzut). "
           "Pusty koszt = pozycja „do wyceny indywidualnej”.")

edited = st.data_editor(
    view, width="stretch", num_rows="fixed", height=520,
    key="cennik_editor",
    column_config={
        "id": st.column_config.TextColumn("ID", disabled=True, width="small"),
        "section": st.column_config.SelectboxColumn("Sekcja", options=sections),
        "name": st.column_config.TextColumn("Nazwa", width="large"),
        "variant": st.column_config.TextColumn("Wariant", width="small"),
        "unit": st.column_config.SelectboxColumn("Jedn.", options=["m2", "szt", "mb"],
                                                 width="small"),
        "base_cost": st.column_config.NumberColumn("Koszt bazowy", format="%.2f"),
        "m_katalog": st.column_config.NumberColumn("Narzut Katalog", format="%.2f"),
        "m_staly": st.column_config.NumberColumn("Narzut Stały", format="%.2f"),
        "m_posrednik": st.column_config.NumberColumn("Narzut Pośrednik", format="%.2f"),
        "m_agencyjny": st.column_config.NumberColumn("Narzut Agencyjny", format="%.2f"),
        "m_jedi": st.column_config.NumberColumn("Narzut Jedi", format="%.2f"),
        "active": st.column_config.CheckboxColumn("Aktywny"),
        "card_file": st.column_config.TextColumn("Karta PDF", disabled=True),
        "note": st.column_config.TextColumn("Notatka"),
        "min_price": st.column_config.NumberColumn(
            "Min. cena/szt", format="%.2f",
            help="Minimalna cena za sztukę — jeśli wyliczona cena jest niższa, "
                 "oferta podbije ją do tej wartości."),
        **{("Cena: " + t): st.column_config.NumberColumn(disabled=True, format="%.2f")
           for t, _ in db.TIERS},
    })

c1, c2, _ = st.columns([1, 2, 3])
if c1.button("💾 Zapisz zmiany", type="primary"):
    save_cols = [c for c in edited.columns if not c.startswith("Cena: ")]
    n = db.save_products_df(edited[save_cols], user="admin")
    st.cache_data.clear()
    st.success("Zapisano. Zmienionych pól: %d." % n)
    st.rerun()

with st.expander("➕ Dodaj nowy produkt"):
    with st.form("add_prod"):
        a1, a2, a3 = st.columns(3)
        n_name = a1.text_input("Nazwa *")
        n_var = a2.text_input("Wariant druku", placeholder="4+0")
        n_sec = a3.selectbox("Sekcja", sections)
        a4, a5 = st.columns(2)
        n_unit = a4.selectbox("Jednostka", ["m2", "szt", "mb"])
        n_cost = a5.number_input("Koszt bazowy (0 = do wyceny)", min_value=0.0,
                                 value=0.0, format="%.2f")
        marks = st.columns(5)
        defaults = [2.5, 1.8, 1.2, 0.75, 0.6]
        vals = [marks[i].number_input("Narzut %s" % t, value=defaults[i],
                                      format="%.2f", key="nm%d" % i)
                for i, (t, _) in enumerate(db.TIERS)]
        if st.form_submit_button("Dodaj") and n_name.strip():
            new = pd.DataFrame([{
                "id": db.next_product_id(), "section": n_sec,
                "name": n_name.strip(), "variant": n_var.strip(),
                "unit": n_unit, "base_cost": n_cost or None,
                "m_katalog": vals[0], "m_staly": vals[1], "m_posrednik": vals[2],
                "m_agencyjny": vals[3], "m_jedi": vals[4],
                "active": 1, "note": "",
            }])
            db.save_products_df(pd.concat([db.products_df(), new],
                                          ignore_index=True), user="admin")
            st.cache_data.clear()
            st.success("Dodano produkt.")
            st.rerun()

with st.expander("⇅ Import / eksport XLSX"):
    up = st.file_uploader("Import cennika (arkusz „Cennik_produkty”)", type=["xlsx"])
    if up and st.button("Importuj"):
        tmp = Path(tempfile.mkstemp(suffix=".xlsx")[1])
        tmp.write_bytes(up.getvalue())
        n = db.import_xlsx(tmp, user="admin-import")
        st.cache_data.clear()
        st.success("Zaimportowano %d pozycji." % n)
        st.rerun()
    if st.button("Przygotuj eksport"):
        out = db.DATA_DIR / "cennik_export.xlsx"
        db.export_xlsx(out)
        st.download_button("⬇️ Pobierz cennik.xlsx", out.read_bytes(),
                           file_name="cennik_ONDRE.xlsx")

with st.expander("🕘 Historia zmian (ostatnie 100)"):
    st.dataframe(db.history_df(100), width="stretch", hide_index=True)
