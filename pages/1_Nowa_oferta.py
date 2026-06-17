"""Nowa oferta: klient → zapytanie (AI) → pozycje → PDF."""
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core import auth, db, pricing
from core.ai_parser import analyze_email
from core.pdf_offer import build_offer_pdf
from core.pipedrive import PipedriveClient
from core.ui import get_secret, page_setup

page_setup("Nowa oferta", "🧾")
user = auth.login_gate()

OUTSIDE = "— pozycja spoza cennika —"
COLS = ["Produkt", "Opis dla klienta", "Ilość", "Szer [m]", "Wys [m]",
        "Cena netto", "Rabat %"]

prod = db.products_df(active_only=True)
prod["label"] = prod.apply(
    lambda r: "%s · %s %s" % (r["id"], r["name"], r["variant"] or ""), axis=1)
prod["label"] = prod["label"].str.strip()
BY_LABEL = prod.set_index("label")
LABELS = [OUTSIDE] + prod["label"].tolist()
BY_ID = prod.set_index("id")


def empty_items():
    return pd.DataFrame(columns=COLS)


ss = st.session_state
ss.setdefault("items", empty_items())
ss.setdefault("client", {})
ss.setdefault("email_text", "")
ss.setdefault("pd_deal", None)

st.title("🧾 Nowa oferta")

# ---------- 1. KLIENT ----------
st.subheader("1 · Klient")
tab_pd, tab_man = st.tabs(["🔌 Z Pipedrive", "✍️ Ręcznie"])

pd_token = get_secret("PIPEDRIVE_API_TOKEN")
with tab_pd:
    if not pd_token:
        st.info("Skonfiguruj PIPEDRIVE_API_TOKEN w sekcji Ustawienia / secrets, "
                "aby wyszukiwać klientów i pobierać maile z deali.")
    else:
        pdc = PipedriveClient(pd_token)
        q = st.text_input("Szukaj firmy w Pipedrive", key="pd_q",
                          placeholder="np. Look Ad")
        if st.button("Szukaj", key="pd_search") and q.strip():
            try:
                ss["pd_results"] = pdc.search_orgs(q.strip())
            except Exception as e:
                st.error("Pipedrive: %s" % e)
        results = ss.get("pd_results") or []
        if results:
            opts = {"%s (id %s)" % (r["name"], r["id"]): r for r in results}
            pick = st.selectbox("Wybierz firmę", list(opts.keys()))
            if st.button("Użyj tej firmy"):
                r = opts[pick]
                try:
                    org = pdc.org(r["id"]) or {}
                except Exception:
                    org = r
                ss["client"] = {
                    "nazwa": org.get("name", r["name"]),
                    "adres": org.get("address") or "",
                    "nip": "", "email": "", "osoba": "",
                    "pipedrive_org_id": r["id"],
                }
                ss["pd_deal"] = None
                st.rerun()

        org_id = ss.get("client", {}).get("pipedrive_org_id")
        if org_id:
            st.success("Klient z Pipedrive: **%s**" % ss["client"]["nazwa"])
            try:
                deals = pdc.org_deals(org_id)
            except Exception as e:
                deals = []
                st.error("Deale: %s" % e)
            if deals:
                dopts = {"#%s · %s" % (d["id"], d.get("title", "")): d["id"]
                         for d in deals}
                dpick = st.selectbox("Powiąż z dealem (opcjonalnie)",
                                     ["—"] + list(dopts.keys()))
                ss["pd_deal"] = dopts.get(dpick)
                if ss["pd_deal"] and st.button("📥 Pobierz maile z deala"):
                    try:
                        msgs = pdc.deal_mail_messages(ss["pd_deal"])
                        ss["pd_msgs"] = [m.get("data", m) for m in msgs]
                    except Exception as e:
                        st.error("Maile: %s" % e)
                for i, m in enumerate(ss.get("pd_msgs") or []):
                    subj = m.get("subject") or "(bez tematu)"
                    snip = (m.get("snippet") or "")[:120]
                    if st.button("✉️ %s — %s…" % (subj, snip), key="msg%d" % i):
                        body = m.get("snippet") or ""
                        try:
                            full = pdc.mail_body(m.get("id"))
                            body = full.get("body") or body
                        except Exception:
                            pass
                        ss["email_text"] = re.sub(r"<[^>]+>", " ", body)
                        st.rerun()

with tab_man:
    c = ss["client"]
    c1, c2 = st.columns(2)
    c["nazwa"] = c1.text_input("Nazwa firmy *", c.get("nazwa", ""))
    c["nip"] = c2.text_input("NIP", c.get("nip", ""))
    c["adres"] = c1.text_input("Adres", c.get("adres", ""))
    c["email"] = c2.text_input("E-mail", c.get("email", ""))
    c["osoba"] = c1.text_input("Osoba kontaktowa", c.get("osoba", ""))
    ss["client"] = c

tier = st.selectbox("Poziom cenowy klienta", db.TIER_NAMES, index=0,
                    help="Steruje narzutem z cennika. Nie jest drukowany na ofercie.")

# ---------- 2. ZAPYTANIE ----------
st.subheader("2 · Zapytanie klienta")
ss["email_text"] = st.text_area(
    "Treść maila / zapytania", ss["email_text"], height=180,
    placeholder="Wklej treść maila od klienta…")

ai_key = get_secret("ANTHROPIC_API_KEY")
cA, cB = st.columns([1, 3])
if cA.button("🤖 Analizuj z AI", type="primary",
             disabled=not (ai_key and ss["email_text"].strip())):
    with st.spinner("Claude analizuje zapytanie…"):
        try:
            res = analyze_email(ss["email_text"], prod, ai_key)
            rows = []
            for p in res.get("pozycje", []):
                pid = p.get("id_produktu")
                label = OUTSIDE
                cena = None
                if pid and pid in BY_ID.index:
                    label = BY_ID.loc[pid, "label"]
                    cena = pricing.price_for(BY_ID.loc[pid], tier)
                uw = p.get("uwagi") or ""
                if (p.get("pewnosc") or 0) < 0.7 and label != OUTSIDE:
                    uw = ("⚠ sprawdź dopasowanie. " + uw).strip()
                rows.append({"Produkt": label,
                             "Opis dla klienta": (p.get("opis_pozycji") or "")
                             + ((" [" + uw + "]") if uw else ""),
                             "Ilość": p.get("ilosc_szt") or 1,
                             "Szer [m]": p.get("szerokosc_m"),
                             "Wys [m]": p.get("wysokosc_m"),
                             "Cena netto": cena, "Rabat %": 0})
            ss["items"] = pd.DataFrame(rows, columns=COLS)
            dk = res.get("dane_klienta") or {}
            for k_src, k_dst in [("firma", "nazwa"), ("osoba", "osoba"),
                                 ("email", "email")]:
                if dk.get(k_src) and not ss["client"].get(k_dst):
                    ss["client"][k_dst] = dk[k_src]
            ss["ai_meta"] = res
            st.rerun()
        except Exception as e:
            st.error("Analiza nie powiodła się: %s" % e)
if not ai_key:
    cB.caption("⚠️ Dodaj ANTHROPIC_API_KEY w secrets, aby włączyć analizę AI.")

meta = ss.get("ai_meta") or {}
if meta:
    info = []
    if meta.get("termin_realizacji"):
        info.append("**Termin z maila:** %s" % meta["termin_realizacji"])
    if meta.get("dodatkowe_informacje"):
        info.append("**Dodatkowo:** %s" % meta["dodatkowe_informacje"])
    if info:
        st.info("  \n".join(info))

# ---------- 3. POZYCJE ----------
st.subheader("3 · Pozycje oferty")

add1, add2 = st.columns([4, 1])
quick = add1.selectbox("Dodaj pozycję z cennika", LABELS, key="quick_add")
if add2.button("➕ Dodaj"):
    cena = None
    if quick != OUTSIDE:
        cena = pricing.price_for(BY_LABEL.loc[quick], tier)
    new = pd.DataFrame([{"Produkt": quick, "Opis dla klienta": "", "Ilość": 1,
                         "Szer [m]": None, "Wys [m]": None,
                         "Cena netto": cena, "Rabat %": 0}])
    ss["items"] = pd.concat([ss["items"], new], ignore_index=True)
    st.rerun()

edited = st.data_editor(
    ss["items"], num_rows="dynamic", width="stretch", key="items_editor",
    column_config={
        "Produkt": st.column_config.SelectboxColumn(options=LABELS, width="large"),
        "Opis dla klienta": st.column_config.TextColumn(width="large"),
        "Ilość": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
        "Szer [m]": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        "Wys [m]": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        "Cena netto": st.column_config.NumberColumn(
            min_value=0.0, format="%.2f",
            help="Puste = „do wyceny”. Edytuj ręcznie lub przelicz z cennika."),
        "Rabat %": st.column_config.NumberColumn(min_value=0, max_value=100,
                                                 step=1, format="%d"),
    })
ss["items"] = edited

b1, b2, _ = st.columns([1.4, 1.6, 3])
if b1.button("↺ Uzupełnij puste ceny"):
    for i, r in edited.iterrows():
        if pd.isna(r["Cena netto"]) and r["Produkt"] in BY_LABEL.index:
            edited.at[i, "Cena netto"] = pricing.price_for(
                BY_LABEL.loc[r["Produkt"]], tier)
    ss["items"] = edited
    st.rerun()
if b2.button("⟳ Nadpisz wszystkie ceny z cennika (%s)" % tier):
    for i, r in edited.iterrows():
        if r["Produkt"] in BY_LABEL.index:
            edited.at[i, "Cena netto"] = pricing.price_for(
                BY_LABEL.loc[r["Produkt"]], tier)
    ss["items"] = edited
    st.rerun()


def to_items(df) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        if pd.isna(r["Produkt"]) and not str(r["Opis dla klienta"] or "").strip():
            continue
        in_cat = r["Produkt"] in BY_LABEL.index
        p = BY_LABEL.loc[r["Produkt"]] if in_cat else None
        item = {
            "produkt_id": p["id"] if in_cat else None,
            "nazwa": ("%s %s" % (p["name"], p["variant"] or "")).strip()
                     if in_cat else "Pozycja indywidualna",
            "opis": str(r["Opis dla klienta"] or "").strip(),
            "ilosc": None if pd.isna(r["Ilość"]) else float(r["Ilość"]),
            "szer": None if pd.isna(r["Szer [m]"]) else float(r["Szer [m]"]),
            "wys": None if pd.isna(r["Wys [m]"]) else float(r["Wys [m]"]),
            "cena": None if pd.isna(r["Cena netto"]) else float(r["Cena netto"]),
            "rabat": 0 if pd.isna(r["Rabat %"]) else float(r["Rabat %"]),
            "unit": p["unit"] if in_cat else "m2",
            "card_file": p["card_file"] if in_cat else None,
        }
        out.append(pricing.compute_item(item))
    return out


items = to_items(edited)
settings = db.get_settings()
net, vat, gross = pricing.totals(items, float(settings["vat_rate"]))
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pozycji", len(items))
m2.metric("Netto", "%.2f zł" % net)
m3.metric("VAT", "%.2f zł" % vat)
m4.metric("Brutto", "%.2f zł" % gross)
if any(i["cena"] is None for i in items):
    st.warning("Niektóre pozycje nie mają ceny — na PDF pojawią się jako „do wyceny”.")

# ---------- 4. GENEROWANIE ----------
st.subheader("4 · Szczegóły i PDF")
d1, d2, d3 = st.columns(3)
number = d1.text_input("Numer oferty", ss.get("offer_no") or "(auto)")
valid_days = d2.number_input("Ważność [dni]",
                             value=int(settings["offer_validity_days"]), min_value=1)
termin = d3.text_input("Termin realizacji",
                       meta.get("termin_realizacji") or "do uzgodnienia")
uwagi = st.text_input("Uwagi na ofercie", "")
attach = st.toggle("Dołącz karty produktowe (PDF) dla pozycji, które je mają",
                   value=True)

cards = []
if attach:
    seen = set()
    for i in items:
        pid = i.get("produkt_id")
        if i.get("card_file") and pid and pid not in seen:
            path = db.materialize_card(pid)
            if path:
                cards.append(path)
                seen.add(pid)
    if cards:
        st.caption("Załączone karty: %d" % len(cards))

if st.button("📄 Generuj ofertę PDF", type="primary",
             disabled=not items or not ss["client"].get("nazwa")):
    no = db.next_offer_number() if number.strip() in ("", "(auto)") else number.strip()
    ss["offer_no"] = no
    today = date.today()
    offer = {
        "number": no,
        "date": today.strftime("%d.%m.%Y"),
        "valid_until": (today + timedelta(days=int(valid_days))).strftime("%d.%m.%Y"),
        "client": ss["client"],
        "issuer": {"name": user["name"], "email": user["email"],
                   "phone": user["phone"]},
        "termin": termin, "uwagi": uwagi,
    }
    fname = re.sub(r"[^\w\-]", "_", "Oferta_%s_%s" % (no, ss["client"]["nazwa"]))[:80] + ".pdf"
    out = db.OFFERS_DIR / fname
    build_offer_pdf(out, offer, items, settings, cards)
    pdf_bytes = out.read_bytes()
    db.save_offer(no, ss["client"], tier, items, net, fname, pdf_bytes,
                  user_id=user["id"], user_name=user["name"], deal_id=ss.get("pd_deal"))
    ss["last_pdf"] = str(out)
    ss["last_pdf_name"] = fname
    st.success("Wygenerowano ofertę **%s**." % no)

if ss.get("last_pdf") and Path(ss["last_pdf"]).exists():
    pdf_bytes = Path(ss["last_pdf"]).read_bytes()
    st.download_button("⬇️ Pobierz PDF", pdf_bytes,
                       file_name=Path(ss["last_pdf"]).name, mime="application/pdf")
    if pd_token and ss.get("pd_deal"):
        if st.button("📤 Załącz PDF do deala w Pipedrive"):
            try:
                PipedriveClient(pd_token).upload_file(ss["pd_deal"], ss["last_pdf"])
                st.success("Plik dodany do deala #%s." % ss["pd_deal"])
            except Exception as e:
                st.error("Wysyłka: %s" % e)
