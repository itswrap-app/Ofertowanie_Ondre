"""Wspólne elementy UI / dostęp do sekretów."""
import os
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "branding" / "logo_color.png"


def get_secret(name, default=""):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


def page_setup(title, icon="🧾"):
    st.set_page_config(page_title="ONDRE Oferty · %s" % title, page_icon=icon,
                       layout="wide")
    if LOGO.exists():
        st.sidebar.image(str(LOGO), width=150)
    st.sidebar.caption("ONDRE · generator ofert")
