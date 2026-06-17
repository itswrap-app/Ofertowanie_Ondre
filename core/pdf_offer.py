"""Generator PDF oferty w identyfikacji ONDRE + doklejanie kart produktowych."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
BRAND = ROOT / "assets" / "branding"

# --- kolory CI ---
BLUE = colors.HexColor("#007DC5")        # Pantone 7461 C
BLUE_DARK = colors.HexColor("#00588A")   # niebieski + 30% K (gradient wg CI)
TINT15 = colors.HexColor("#D8ECF6")      # 15% niebieskiego
TINT35 = colors.HexColor("#A6D2EC")
GRAY = colors.HexColor("#444444")
LIGHT = colors.HexColor("#777777")


def _register_fonts():
    """Apertura (jeśli pliki w assets/fonts) → fallback DejaVu (polskie znaki)."""
    pairs = [
        ("ONDRE", ["Apertura-Regular.ttf", "Apertura-Regular.otf", "DejaVuSans.ttf"]),
        ("ONDRE-Bold", ["Apertura-Bold.ttf", "Apertura-Bold.otf",
                        "Apertura-Black.ttf", "DejaVuSans-Bold.ttf"]),
    ]
    for alias, candidates in pairs:
        for c in candidates:
            p = FONTS / c
            if p.exists():
                try:
                    pdfmetrics.registerFont(TTFont(alias, str(p)))
                    break
                except Exception:
                    continue
    reg = pdfmetrics.getRegisteredFontNames()
    return ("ONDRE" if "ONDRE" in reg else "Helvetica",
            "ONDRE-Bold" if "ONDRE-Bold" in reg else "Helvetica-Bold")


F_REG, F_BOLD = _register_fonts()

S_BASE = ParagraphStyle("base", fontName=F_REG, fontSize=9, leading=12,
                        textColor=colors.black)
S_SMALL = ParagraphStyle("small", parent=S_BASE, fontSize=7.5, leading=9.5,
                         textColor=GRAY)
S_H = ParagraphStyle("h", fontName=F_BOLD, fontSize=11, leading=14,
                     textColor=BLUE, spaceBefore=6, spaceAfter=3)
S_CELL = ParagraphStyle("cell", parent=S_BASE, fontSize=8.5, leading=10.5)
S_CELL_DESC = ParagraphStyle("celldesc", parent=S_BASE, fontSize=7.5,
                             leading=9, textColor=LIGHT)


class _NumberedCanvas(rl_canvas.Canvas):
    """Numeracja 'Strona X z Y'."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont(F_REG, 7.5)
            self.setFillColor(LIGHT)
            self.drawRightString(A4[0] - 15 * mm, 9 * mm,
                                 "Strona %d z %d" % (self._pageNumber, total))
            super().showPage()
        super().save()


def _gradient_band(canv, x, y, w, h, c1=BLUE, c2=BLUE_DARK, steps=60):
    r1, g1, b1 = c1.red, c1.green, c1.blue
    r2, g2, b2 = c2.red, c2.green, c2.blue
    sw = w / steps
    for i in range(steps):
        t = i / (steps - 1)
        canv.setFillColorRGB(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t,
                             b1 + (b2 - b1) * t)
        canv.rect(x + i * sw, y, sw + 0.6, h, stroke=0, fill=1)


def _logo(canv, x, y, h, white=True):
    f = BRAND / ("logo_white.png" if white else "logo_color.png")
    if f.exists():
        from reportlab.lib.utils import ImageReader
        img = ImageReader(str(f))
        iw, ih = img.getSize()
        w = h * iw / ih
        canv.drawImage(img, x, y, width=w, height=h, mask="auto")
        return w
    return 0


def _make_pages(settings, number, date_str):
    W, H = A4

    def footer(canv):
        canv.setStrokeColor(BLUE)
        canv.setLineWidth(0.8)
        canv.line(15 * mm, 16 * mm, W - 15 * mm, 16 * mm)
        canv.setFont(F_REG, 7.5)
        canv.setFillColor(GRAY)
        l1 = "%s · %s" % (settings["company_name"], settings["company_address"])
        parts = ["NIP %s" % settings["company_nip"]]
        if settings.get("company_regon"):
            parts.append("REGON %s" % settings["company_regon"])
        parts += ["E: %s" % settings["company_email"],
                  "T: %s" % settings["company_phone"], settings["company_web"]]
        canv.drawString(15 * mm, 12 * mm, l1)
        canv.drawString(15 * mm, 8.5 * mm, "  ·  ".join(parts))

    def first(canv, doc):
        canv.saveState()
        _gradient_band(canv, 0, H - 34 * mm, W, 34 * mm)
        _logo(canv, 15 * mm, H - 24.5 * mm, 11 * mm, white=True)
        canv.setFillColor(colors.white)
        canv.setFont(F_BOLD, 17)
        canv.drawRightString(W - 15 * mm, H - 17 * mm, "OFERTA HANDLOWA")
        canv.setFont(F_REG, 10)
        canv.drawRightString(W - 15 * mm, H - 24 * mm,
                             "Nr %s   ·   %s" % (number, date_str))
        footer(canv)
        canv.restoreState()

    def later(canv, doc):
        canv.saveState()
        canv.setFillColor(BLUE)
        canv.rect(0, H - 14 * mm, W, 14 * mm, stroke=0, fill=1)
        _logo(canv, 15 * mm, H - 11 * mm, 7 * mm, white=True)
        canv.setFillColor(colors.white)
        canv.setFont(F_REG, 9)
        canv.drawRightString(W - 15 * mm, H - 9.5 * mm, "Oferta nr %s" % number)
        footer(canv)
        canv.restoreState()

    f_first = Frame(15 * mm, 20 * mm, W - 30 * mm, H - 34 * mm - 26 * mm, id="f1")
    f_later = Frame(15 * mm, 20 * mm, W - 30 * mm, H - 14 * mm - 26 * mm, id="f2")
    return (PageTemplate(id="first", frames=[f_first], onPage=first),
            PageTemplate(id="later", frames=[f_later], onPage=later))


def _fmt(v, dec=2, suffix=""):
    if v in (None, ""):
        return "—"
    s = ("{:,.%df}" % dec).format(float(v)).replace(",", " ").replace(".", ",")
    return s + suffix


def build_offer_pdf(out_path, offer: dict, items: list, settings: dict,
                    card_paths: list | None = None) -> Path:
    """offer: number, date, valid_until, client{nazwa,adres,nip,email,osoba},
    issuer{name,email,phone}, termin, uwagi. items: policzona lista pozycji."""
    out_path = Path(out_path)
    tmp = out_path.with_suffix(".body.pdf")

    doc = BaseDocTemplate(str(tmp), pagesize=A4, title="Oferta %s" % offer["number"],
                          author=settings["company_name"])
    t1, t2 = _make_pages(settings, offer["number"], offer["date"])
    doc.addPageTemplates([t1, t2])

    story = [_switch_template()]

    # --- blok: odbiorca / dane oferty ---
    cl = offer["client"]
    left = ["<font name='%s' size='8' color='#777777'>OFERTA DLA:</font>" % F_REG,
            "<b>%s</b>" % (cl.get("nazwa") or "—")]
    if cl.get("adres"):
        left.append(cl["adres"])
    if cl.get("nip"):
        left.append("NIP: %s" % cl["nip"])
    if cl.get("osoba"):
        left.append("Do rąk: %s" % cl["osoba"])
    if cl.get("email"):
        left.append(cl["email"])

    iss = offer.get("issuer") or {}
    right = ["<font name='%s' size='8' color='#777777'>DANE OFERTY:</font>" % F_REG,
             "Data wystawienia: <b>%s</b>" % offer["date"],
             "Oferta ważna do: <b>%s</b>" % offer["valid_until"]]
    if iss.get("name"):
        right.append("Osoba kontaktowa: <b>%s</b>" % iss["name"])
        contact = " · ".join(x for x in [iss.get("email"), iss.get("phone")] if x)
        if contact:
            right.append(contact)

    meta = Table(
        [[Paragraph("<br/>".join(left), S_BASE),
          Paragraph("<br/>".join(right), S_BASE)]],
        colWidths=[100 * mm, 80 * mm])
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [Spacer(1, 4 * mm), meta, Spacer(1, 5 * mm)]

    # --- tabela pozycji ---
    head = ["Lp.", "Nazwa / opis pozycji", "Wymiar [m]", "Ilość",
            "Cena/m²", "Cena/szt", "Rab.", "Wartość netto"]
    data = [head]
    for i, it in enumerate(items, 1):
        nazwa = "<b>%s</b>" % it["nazwa"]
        if it.get("opis"):
            nazwa += "<br/><font size='7.5' color='#777777'>%s</font>" % it["opis"]
        dim = ("%s × %s" % (_fmt(it["szer"]), _fmt(it["wys"]))
               if it.get("szer") and it.get("wys") else "—")
        cm2 = _fmt(it["cena_m2"], 2, " zł") if it.get("cena_m2") not in (None, "") else "—"
        cszt = (_fmt(it["cena_szt"], 2, " zł") if it.get("cena_szt") not in (None, "")
                else "do wyceny")
        wart = _fmt(it.get("wartosc"), 2, " zł") if it.get("wartosc") is not None else "—"
        data.append([str(i), Paragraph(nazwa, S_CELL), dim,
                     _fmt(it.get("ilosc"), 0), cm2, cszt,
                     _fmt(it.get("rabat"), 0, "%"), wart])

    tbl = Table(data, colWidths=[9 * mm, 54 * mm, 19 * mm, 11 * mm, 21 * mm,
                                 21 * mm, 11 * mm, 24 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), F_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), F_REG),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBD7EA")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for r in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, r), (-1, r), TINT15))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    # --- podsumowanie ---
    net = sum(i["wartosc"] for i in items if i.get("wartosc"))  # items są już policzone (NaN odfiltrowane wyżej)
    vat_rate = float(settings.get("vat_rate", 23))
    vat = round(net * vat_rate / 100, 2)
    tot = Table([
        ["Suma netto:", _fmt(net, 2, " zł")],
        ["VAT %s%%:" % _fmt(vat_rate, 0), _fmt(vat, 2, " zł")],
        ["RAZEM BRUTTO:", _fmt(net + vat, 2, " zł")],
    ], colWidths=[40 * mm, 32 * mm], hAlign="RIGHT")
    tot.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), F_REG),
        ("FONTNAME", (0, 2), (-1, 2), F_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 2), (-1, 2), BLUE),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, BLUE),
    ]))
    story += [Spacer(1, 3 * mm), tot, Spacer(1, 5 * mm)]

    if any(i.get("wartosc") in (None, "") for i in items):
        story.append(Paragraph(
            "* Pozycje oznaczone „do wyceny” zostaną wycenione indywidualnie "
            "po doprecyzowaniu specyfikacji.", S_SMALL))

    # --- warunki ---
    if offer.get("termin"):
        story += [Paragraph("Termin realizacji", S_H),
                  Paragraph(offer["termin"], S_BASE)]
    if offer.get("uwagi"):
        story += [Paragraph("Uwagi", S_H), Paragraph(offer["uwagi"], S_BASE)]
    story += [Paragraph("Warunki", S_H),
              Paragraph(settings.get("payment_terms", ""), S_BASE)]
    if settings.get("company_bank"):
        story.append(Paragraph("Nr konta: %s" % settings["company_bank"], S_BASE))
    if card_paths:
        story.append(Paragraph(
            "Załączniki: karty produktowe (%d) — na kolejnych stronach."
            % len(card_paths), S_BASE))

    story += [Spacer(1, 10 * mm),
              Paragraph("Z poważaniem,<br/><b>%s</b><br/>%s"
                        % (iss.get("name") or settings["company_name"],
                           settings["company_name"]), S_BASE)]

    doc.build(story, canvasmaker=_NumberedCanvas)

    # --- doklejenie kart produktowych ---
    if card_paths:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for p in [tmp] + [Path(c) for c in card_paths]:
            try:
                for page in PdfReader(str(p)).pages:
                    writer.add_page(page)
            except Exception:
                continue
        with open(out_path, "wb") as f:
            writer.write(f)
        tmp.unlink(missing_ok=True)
    else:
        tmp.replace(out_path)
    return out_path


def _switch_template():
    from reportlab.platypus import NextPageTemplate
    return NextPageTemplate("later")
