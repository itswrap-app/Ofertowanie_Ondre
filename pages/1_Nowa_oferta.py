"""Nowa oferta: klient → czat z AI → pozycje (ceny m²/szt, przeliczanie na żywo) → PDF."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core import auth, db, pricing
from core.ai_parser import catalog_block, chat_offer
from core.pdf_offer import build_offer_pdf
from core.pipedrive import PipedriveClient
from core.ui import get_secret, page_setup

page_setup("Nowa oferta", "🧾")
user = auth.login_gate()

OUTSIDE = "— pozycja spoza cennika —"
EDIT_COLS = ["Produkt", "Opis dla klienta", "Ilość", "Szer [m]", "Wys [m]",
             "Cena/m²", "Cena/szt", "Rabat %"]
CALC_COLS = ["Pow [m²]", "Wartość"]
COLS = EDIT_COLS + CALC_COLS

prod = db.products_df(active_only=True)
prod["label"] = prod.apply(
    lambda r: ("%s · %s %s" % (r["id"], r["name"], r["variant"] or "")).strip(), axis=1)
BY_LABEL = prod.set_index("label")
LABELS = [OUTSIDE] + prod["label"].tolist()
BY_ID = prod.set_index("id")
_f = pricing._f


def empty_items():
    return pd.DataFrame(columns=COLS)


def _eq(a, b):
    fa, fb = _f(a), _f(b)
    if fa is None and fb is None:
        return True
    if fa is None or fb is None:
        return False
    return abs(fa - fb) < 1e-9


def base_prices(label, tier):
    """Zwraca (cena_m2, cena_szt) z cennika dla danej etykiety i poziomu."""
    if label not in BY_LABEL.index:
        return None, None
    prow = BY_LABEL.loc[label]
    base = pricing.price_for(prow, tier)
    if (prow.get("unit") or "m2") == "m2":
        return base, None
    return None, base


def rows_from_pozycje(pozycje, tier, prev_df=None):
    prevmap = {}
    if prev_df is not None:
        for _, r in prev_df.iterrows():
            prevmap.setdefault(r["Produkt"], (r["Cena/m²"], r["Cena/szt"]))
    rows = []
    for p in pozycje:
        pid = p.get("id_produktu")
        label = BY_ID.loc[pid, "label"] if (pid and pid in BY_ID.index) else OUTSIDE
        ilosc = p.get("ilosc_szt") or 1
        ai_tot, ai_szt, ai_m2 = _f(p.get("cena_calosc")), _f(p.get("cena_szt")), _f(p.get("cena_m2"))
        if ai_tot is not None and ilosc:          # cena podana w czacie ma priorytet
            cm2, cszt = None, round(ai_tot / float(ilosc), 4)
        elif ai_szt is not None:
            cm2, cszt = None, ai_szt
        elif ai_m2 is not None:
            cm2, cszt = ai_m2, None
        else:                                      # brak ceny od AI → cennik / korekty ręczne
            cm2, cszt = base_prices(label, tier)
            if label in prevmap and label != OUTSIDE:
                pc2, pcs = prevmap[label]
                if not pd.isna(pc2):
                    cm2 = pc2
                if cm2 is None and not pd.isna(pcs):
                    cszt = pcs
        uw = (p.get("uwagi") or "").strip()
        if (p.get("pewnosc") or 0) < 0.7 and label != OUTSIDE:
            uw = ("⚠ sprawdź dopasowanie. " + uw).strip()
        opis = (p.get("opis_pozycji") or "")
        if uw:
            opis = (opis + "  [" + uw + "]").strip()
        rows.append({"Produkt": label, "Opis dla klienta": opis,
                     "Ilość": ilosc,
                     "Szer [m]": p.get("szerokosc_m"), "Wys [m]": p.get("wysokosc_m"),
                     "Cena/m²": cm2, "Cena/szt": cszt, "Rabat %": 0,
                     "Pow [m²]": None, "Wartość": None})
    return pd.DataFrame(rows, columns=COLS)


def recalc(df, prev=None):
    df = df.reindex(columns=COLS).copy()
    for idx in df.index:
        r = df.loc[idx]
        label = r["Produkt"]
        minp = BY_LABEL.loc[label, "min_price"] if label in BY_LABEL.index else None
        driver = None
        if prev is not None and idx in prev.index:
            if not _eq(prev.at[idx, "Cena/m²"], r["Cena/m²"]):
                driver = "m2"
            elif not _eq(prev.at[idx, "Cena/szt"], r["Cena/szt"]):
                driver = "szt"
        res = pricing.compute_line(r["Ilość"], r["Szer [m]"], r["Wys [m]"],
                                   r["Cena/m²"], r["Cena/szt"], r["Rabat %"],
                                   min_price=minp, driver=driver)
        df.at[idx, "Cena/m²"] = res["cena_m2"]
        df.at[idx, "Cena/szt"] = res["cena_szt"]
        df.at[idx, "Pow [m²]"] = res["pow"]
        df.at[idx, "Wartość"] = res["wartosc"]
    return df


ss = st.session_state
ss.setdefault("items", empty_items())
ss.setdefault("client", {})
ss.setdefault("email_text", "")
ss.setdefault("pd_deal", None)
ss.setdefault("chat_api", [])
ss.setdefault("chat_display", [])
ss.setdefault("ai_meta", {})

st.title("🧾 Nowa oferta")

# ---------- 1. KLIENT ----------
st.subheader("1 · Klient")
tab_pd, tab_man = st.tabs(["🔌 Z Pipedrive", "✍️ Ręcznie"])
pd_token = get_secret("PIPEDRIVE_API_TOKEN")
with tab_pd:
    if not pd_token:
        st.info("Skonfiguruj PIPEDRIVE_API_TOKEN w Ustawieniach, aby wyszukiwać klientów.")
    else:
        pdc = PipedriveClient(pd_token)
        q = st.text_input("Szukaj firmy w Pipedrive", key="pd_q", placeholder="np. Look Ad")
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
                ss["client"] = {"nazwa": org.get("name", r["name"]),
                                "adres": org.get("address") or "", "nip": "",
                                "email": "", "osoba": "", "pipedrive_org_id": r["id"]}
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
                dopts = {"#%s · %s" % (d["id"], d.get("title", "")): d["id"] for d in deals}
                dpick = st.selectbox("Powiąż z dealem (opcjonalnie)", ["—"] + list(dopts.keys()))
                ss["pd_deal"] = dopts.get(dpick)
                if ss["pd_deal"] and st.button("📥 Pobierz maile z deala"):
                    try:
                        msgs = pdc.deal_mail_messages(ss["pd_deal"])
                        ss["pd_msgs"] = [m.get("data", m) for m in msgs]
                    except Exception as e:
                        st.error("Maile: %s" % e)
                for i, m in enumerate(ss.get("pd_msgs") or []):
                    subj = m.get("subject") or "(bez tematu)"
                    if st.button("✉️ %s — %s…" % (subj, (m.get("snippet") or "")[:90]),
                                 key="msg%d" % i):
                        body = m.get("snippet") or ""
                        try:
                            body = (pdc.mail_body(m.get("id")) or {}).get("body") or body
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
    c["telefon"] = c2.text_input("Telefon", c.get("telefon", ""))
    ss["client"] = c

tier = st.selectbox("Poziom cenowy klienta", db.TIER_NAMES, index=0, key="tier",
                    help="Steruje narzutem z cennika. Nie jest drukowany na ofercie.")

# ---------- 2. CZAT Z AI ----------
st.subheader("2 · Zapytanie i czat z AI")
ai_key = get_secret("ANTHROPIC_API_KEY")
ss["email_text"] = st.text_area("Treść maila / zapytania", ss["email_text"], height=160,
                                placeholder="Wklej treść maila od klienta…")


def call_claude(user_content, seed=False):
    backup_api, backup_disp = list(ss["chat_api"]), list(ss["chat_display"])
    if seed:
        ss["chat_api"] = [{"role": "user", "content": user_content}]
        ss["chat_display"] = []
    else:
        ss["chat_api"].append({"role": "user", "content": user_content})
        ss["chat_display"].append({"role": "user", "text": user_content.split("\n\n[")[0]})
    try:
        with st.spinner("Claude pracuje…"):
            data, raw = chat_offer(ss["chat_api"], ai_key)
    except Exception:
        ss["chat_api"], ss["chat_display"] = backup_api, backup_disp   # rollback
        raise
    ss["chat_api"].append({"role": "assistant", "content": raw})
    ss["chat_display"].append({"role": "assistant", "text": data.get("wiadomosc", "")})
    ss["items"] = recalc(rows_from_pozycje(data.get("pozycje", []), tier,
                                           ss["items"] if not seed else None))
    ss["ai_meta"] = {"termin_realizacji": data.get("termin_realizacji"),
                     "dodatkowe_informacje": data.get("dodatkowe_informacje")}
    dk = data.get("dane_klienta") or {}
    for a, b in [("firma", "nazwa"), ("osoba", "osoba"), ("email", "email"),
                 ("telefon", "telefon"), ("adres", "adres"), ("nip", "nip")]:
        if dk.get(a) and not ss["client"].get(b):
            ss["client"][b] = dk[a]


col_a, col_b = st.columns([1, 2])
if col_a.button("▶️ Przeanalizuj i rozpocznij czat", type="primary",
                disabled=not (ai_key and ss["email_text"].strip())):
    content = ("CENNIK (id | sekcja | nazwa | wariant | dostępność ceny):\n"
               + catalog_block(prod) + "\n\n---\nZAPYTANIE KLIENTA:\n" + ss["email_text"].strip())
    try:
        call_claude(content, seed=True)
        st.rerun()
    except Exception as e:
        st.error("Błąd AI: %s" % e)
if not ai_key:
    col_b.caption("⚠️ Dodaj ANTHROPIC_API_KEY w Secrets, aby włączyć AI.")
elif ss["chat_display"]:
    if col_b.button("🗑 Wyczyść czat i zacznij od nowa"):
        ss["chat_api"], ss["chat_display"], ss["ai_meta"] = [], [], {}
        st.rerun()

# historia czatu + pole do korekty
for m in ss["chat_display"]:
    with st.chat_message("user" if m["role"] == "user" else "assistant"):
        st.markdown(m["text"] or "_(brak treści)_")

if ss["chat_display"]:
    prompt = st.chat_input("Doprecyzuj dla Claude, np. „D-Bond przyjmij z laminatem”…")
    if prompt:
        table_state = [{"produkt": r["Produkt"], "opis": r["Opis dla klienta"],
                        "ilosc": r["Ilość"], "szer": r["Szer [m]"], "wys": r["Wys [m]"]}
                       for _, r in ss["items"].iterrows()]
        content = (prompt + "\n\n[Aktualny stan pozycji w tabeli po zmianach handlowca:]\n"
                   + json.dumps(table_state, ensure_ascii=False, default=str))
        try:
            call_claude(content)
            st.rerun()
        except Exception as e:
            st.error("Błąd AI: %s" % e)

meta = ss.get("ai_meta") or {}
info = []
if meta.get("termin_realizacji"):
    info.append("**Termin z maila:** %s" % meta["termin_realizacji"])
if meta.get("dodatkowe_informacje"):
    info.append("**Dodatkowo:** %s" % meta["dodatkowe_informacje"])
if info:
    st.info("  \n".join(info))

cl_sum = ss.get("client") or {}
if any(cl_sum.get(k) for k in ("nazwa", "osoba", "email", "telefon", "nip", "adres")):
    bits = []
    if cl_sum.get("nazwa"):
        bits.append("**%s**" % cl_sum["nazwa"])
    for icon, k in [("👤", "osoba"), ("✉️", "email"), ("📞", "telefon"),
                    ("🏷️ NIP", "nip"), ("📍", "adres")]:
        if cl_sum.get(k):
            bits.append("%s %s" % (icon, cl_sum[k]))
    st.caption("Dane klienta: " + "  ·  ".join(bits))

# ---------- 3. POZYCJE ----------
st.subheader("3 · Pozycje oferty")
st.caption("Edytuj **Cena/m²** lub **Cena/szt** — druga przeliczy się sama. Zmiana ilości, "
           "wymiarów i rabatu również przelicza wartość na bieżąco.")

add1, add2 = st.columns([4, 1])
quick = add1.selectbox("Dodaj pozycję z cennika", LABELS, key="quick_add")
if add2.button("➕ Dodaj"):
    cm2, cszt = base_prices(quick, tier)
    new = pd.DataFrame([{"Produkt": quick, "Opis dla klienta": "", "Ilość": 1,
                         "Szer [m]": None, "Wys [m]": None, "Cena/m²": cm2,
                         "Cena/szt": cszt, "Rabat %": 0, "Pow [m²]": None, "Wartość": None}])
    ss["items"] = recalc(pd.concat([ss["items"], new], ignore_index=True))
    st.rerun()

input_df = ss["items"].reindex(columns=COLS)
edited = st.data_editor(
    input_df, num_rows="dynamic", width="stretch", key="items_editor",
    disabled=["Pow [m²]", "Wartość"],
    column_config={
        "Produkt": st.column_config.SelectboxColumn(options=LABELS, width="large"),
        "Opis dla klienta": st.column_config.TextColumn(width="large"),
        "Ilość": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
        "Szer [m]": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        "Wys [m]": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        "Cena/m²": st.column_config.NumberColumn(min_value=0.0, format="%.2f zł",
                                                 help="Cena za metr kwadratowy."),
        "Cena/szt": st.column_config.NumberColumn(min_value=0.0, format="%.2f zł",
                                                  help="Cena za sztukę (liczy się z ceny/m², "
                                                       "lub wpisz wprost dla pozycji od sztuki)."),
        "Rabat %": st.column_config.NumberColumn(min_value=0, max_value=100, step=1, format="%d"),
        "Pow [m²]": st.column_config.NumberColumn(format="%.3f", help="Powierzchnia łączna."),
        "Wartość": st.column_config.NumberColumn(format="%.2f zł", help="Wartość netto pozycji."),
    })
recalced = recalc(edited, input_df)
ss["items"] = recalced

b1, b2, _sp = st.columns([1.5, 1.8, 3])
if b1.button("↺ Uzupełnij puste ceny"):
    df = ss["items"]
    for i, r in df.iterrows():
        if pd.isna(r["Cena/m²"]) and pd.isna(r["Cena/szt"]):
            cm2, cszt = base_prices(r["Produkt"], tier)
            df.at[i, "Cena/m²"], df.at[i, "Cena/szt"] = cm2, cszt
    ss["items"] = recalc(df)
    st.rerun()
if b2.button("⟳ Nadpisz ceny z cennika (%s)" % tier):
    df = ss["items"]
    for i, r in df.iterrows():
        cm2, cszt = base_prices(r["Produkt"], tier)
        df.at[i, "Cena/m²"], df.at[i, "Cena/szt"] = cm2, cszt
    ss["items"] = recalc(df)
    st.rerun()


def to_items(df):
    out = []
    for _, r in df.iterrows():
        empty = (r["Produkt"] in (None, OUTSIDE) or pd.isna(r["Produkt"]))
        if empty and not str(r["Opis dla klienta"] or "").strip() \
                and pd.isna(r["Cena/szt"]) and pd.isna(r["Cena/m²"]):
            continue
        in_cat = r["Produkt"] in BY_LABEL.index
        p = BY_LABEL.loc[r["Produkt"]] if in_cat else None
        out.append({
            "produkt_id": p["id"] if in_cat else None,
            "nazwa": ("%s %s" % (p["name"], p["variant"] or "")).strip()
                     if in_cat else "Pozycja indywidualna",
            "opis": str(r["Opis dla klienta"] or "").strip(),
            "ilosc": _f(r["Ilość"]), "szer": _f(r["Szer [m]"]), "wys": _f(r["Wys [m]"]),
            "cena_m2": _f(r["Cena/m²"]), "cena_szt": _f(r["Cena/szt"]),
            "pow": _f(r["Pow [m²]"]), "wartosc": _f(r["Wartość"]),
            "rabat": _f(r["Rabat %"]) or 0,
            "card_file": p["card_file"] if in_cat else None,
            "unit": p["unit"] if in_cat else "m2",
        })
    return out


items = to_items(ss["items"])
settings = db.get_settings()
net, vat, gross = pricing.totals(items, float(settings["vat_rate"]))
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pozycji", len(items))
m2.metric("Netto", "%.2f zł" % net)
m3.metric("VAT", "%.2f zł" % vat)
m4.metric("Brutto", "%.2f zł" % gross)
if any(i["wartosc"] is None for i in items):
    st.warning("Pozycje bez ceny pojawią się na PDF jako „do wyceny”.")

# ---------- 4. GENEROWANIE ----------
st.subheader("4 · Szczegóły i PDF")
d1, d2, d3 = st.columns(3)
number = d1.text_input("Numer oferty", ss.get("offer_no") or "(auto)")
valid_days = d2.number_input("Ważność [dni]", value=int(settings["offer_validity_days"]), min_value=1)
termin = d3.text_input("Termin realizacji", meta.get("termin_realizacji") or "do uzgodnienia")
uwagi = st.text_input("Uwagi na ofercie", "")
attach = st.toggle("Dołącz karty produktowe (PDF) dla pozycji, które je mają", value=True)

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
    offer = {"number": no, "date": today.strftime("%d.%m.%Y"),
             "valid_until": (today + timedelta(days=int(valid_days))).strftime("%d.%m.%Y"),
             "client": ss["client"],
             "issuer": {"name": user["name"], "email": user["email"], "phone": user["phone"]},
             "termin": termin, "uwagi": uwagi}
    fname = re.sub(r"[^\w\-]", "_", "Oferta_%s_%s" % (no, ss["client"]["nazwa"]))[:80] + ".pdf"
    out = db.OFFERS_DIR / fname
    build_offer_pdf(out, offer, items, settings, cards)
    pdf_bytes = out.read_bytes()
    db.save_offer(no, ss["client"], tier, items, net, fname, pdf_bytes,
                  user_id=user["id"], user_name=user["name"], deal_id=ss.get("pd_deal"))
    ss["last_pdf"] = str(out)
    st.success("Wygenerowano ofertę **%s**." % no)

if ss.get("last_pdf") and Path(ss["last_pdf"]).exists():
    st.download_button("⬇️ Pobierz PDF", Path(ss["last_pdf"]).read_bytes(),
                       file_name=Path(ss["last_pdf"]).name, mime="application/pdf")

    if pd_token:
        st.markdown("**➕ Dodaj do Pipedrive (szansa sprzedaży)**")
        pdc2 = PipedriveClient(pd_token)
        org_id = ss.get("client", {}).get("pipedrive_org_id")
        if "pd_pipelines" not in ss:
            try:
                ss["pd_pipelines"] = pdc2.list_pipelines()
            except Exception as e:
                ss["pd_pipelines"] = []
                st.caption("Nie udało się pobrać lejków: %s" % e)
        pl_opts = {p["name"]: p["id"] for p in (ss.get("pd_pipelines") or [])}
        cp1, cp2 = st.columns([2, 3])
        pl_pick = cp1.selectbox("Lejek (pipeline)", list(pl_opts.keys()) or ["—"])
        title = cp2.text_input("Tytuł szansy", "Oferta %s – %s"
                               % (ss.get("offer_no", ""), ss["client"].get("nazwa", "")))
        if not org_id:
            st.caption("ℹ️ Klient nie pochodzi z Pipedrive — szansa powstanie bez powiązanej firmy "
                       "(możesz ją podpiąć w Pipedrive po utworzeniu).")
        bb1, bb2 = st.columns(2)
        if ss.get("pd_deal") and bb1.button("📎 Dołącz PDF do wybranego deala #%s" % ss["pd_deal"]):
            try:
                pdc2.upload_file(ss["pd_deal"], ss["last_pdf"])
                st.success("PDF dodany do deala #%s." % ss["pd_deal"])
            except Exception as e:
                st.error("Pipedrive: %s" % e)
        if bb2.button("➕ Utwórz szansę i dołącz PDF", type="primary", disabled=not pl_opts):
            try:
                deal = pdc2.create_deal(title, value=round(net, 2), currency="PLN",
                                        org_id=org_id, pipeline_id=pl_opts.get(pl_pick))
                pdc2.upload_file(deal["id"], ss["last_pdf"])
                st.success("Utworzono szansę **#%s** (%.2f zł netto) w lejku „%s” i dołączono PDF."
                           % (deal["id"], net, pl_pick))
            except Exception as e:
                st.error("Pipedrive: %s" % e)
