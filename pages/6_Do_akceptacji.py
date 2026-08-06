"""Do akceptacji — nowe nośniki zgłoszone przez handlowców (tylko admin)."""
import streamlit as st

from core import auth, db, pricing
from core.ui import page_setup

page_setup("Do akceptacji", "✅")
auth.login_gate()
auth.require_admin()

st.title("✅ Do akceptacji")
st.caption("Nowe nośniki zgłoszone przez handlowców. Po zatwierdzeniu trafiają do cennika.")

pend = db.pending_products()
if pend.empty:
    st.success("Brak zgłoszeń oczekujących na akceptację.")
    st.stop()

st.write("Oczekujących: **%d**" % len(pend))
for _, r in pend.iterrows():
    with st.container(border=True):
        st.markdown("### %s  ·  _%s_" % (r["name"], r["section"] or "bez kategorii"))
        prices = []
        for tname, tcol in db.TIERS:
            p = pricing.unit_price(r["base_cost"], r[tcol])
            prices.append("%s: %s" % (tname, ("%.2f zł" % p) if p is not None else "—"))
        st.caption("Zgłosił: %s · jednostka: %s · koszt: %s · min. wartość: %s zł" % (
            r.get("created_by") or "—", r["unit"],
            ("%.2f zł" % r["base_cost"]) if r["base_cost"] else "—",
            ("%.0f" % r["min_price"]) if r["min_price"] else "—"))
        st.write("Ceny: " + "  ·  ".join(prices))
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("✅ Zaakceptuj", key="ok_%s" % r["id"], type="primary"):
            db.approve_product(r["id"], user=auth.current_user()["name"])
            st.cache_data.clear()
            st.success("Dodano „%s” do cennika." % r["name"])
            st.rerun()
        if c2.button("🗑 Odrzuć", key="no_%s" % r["id"]):
            db.reject_product(r["id"], user=auth.current_user()["name"])
            st.cache_data.clear()
            st.rerun()
