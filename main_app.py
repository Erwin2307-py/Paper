import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

from modules.online_api_filter import module_online_api_filter

# ------------------------------------------------------------
# EINMALIGE set_page_config(...) 
# ------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

###############################################################################
# 0) LOGIN-FUNKTION
###############################################################################

def show_login():
    """Zeigt das Login-Formular und das Willkommensbild an (nebeneinander)."""
    # Du kannst columns anlegen, wenn du Bild/Eingabe nebeneinander haben möchtest:
    col_img, col_form = st.columns([1,1])

    with col_img:
        st.title("Bitte zuerst einloggen")
        st.image("Bild1.jpg", caption="Willkommen!", use_container_width=True)

    with col_form:
        st.write("## Login eingeben:")
        user = st.text_input("Benutzername:")
        pw = st.text_input("Passwort:", type="password")

        if st.button("Einloggen"):
            # Beispielhafter Check der Zugangsdaten (hier noch hartkodiert!)
            # Ersetze das durch st.secrets["login"]["username"] / ["password"], wenn gewünscht
            if user == "demo" and pw == "secret":
                st.session_state["logged_in"] = True
                st.success("Erfolgreich eingeloggt! Navigationsleiste wird eingeblendet ...")
                # Durch rerun wird das Skript neu geladen => Sidebar angezeigt
                st.experimental_rerun()
            else:
                st.error("Falsche Anmeldedaten. Bitte erneut versuchen.")


###############################################################################
# 1) Gemeinsame Funktionen & Klassen
###############################################################################

class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=100):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = []
            for key, value in filters.items():
                filter_expressions.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort
        r = requests.get(
            self.base_url + endpoint,
            headers=self.headers,
            params=params,
            timeout=15
        )
        r.raise_for_status()
        return r.json()

def check_core_aggregate_connection(api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF", timeout=15):
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query, api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"):
    if not api_key:
        return []
    try:
        core = CoreAPI(api_key)
        raw = core.search_publications(query, limit=100)
        out = []
        results = raw.get("results", [])
        for item in results:
            title = item.get("title", "n/a")
            year = str(item.get("yearPublished", "n/a"))
            journal = item.get("publisher", "n/a")
            out.append({
                "PMID": "n/a",
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"CORE search error: {e}")
        return []


###############################################################################
# (PubMed-Funktionen, EuropePMC, etc. bleiben unverändert)
# ...

###############################################################################
# 3) Pages
###############################################################################

def module_paperqa2():
    st.subheader("PaperQA2 Module")
    question = st.text_input("Bitte gib deine Frage ein:")
    if st.button("Frage absenden"):
        st.write("Antwort: (Dummy) ...", question)

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Du bist erfolgreich eingeloggt! Wähle ein Modul in der Sidebar aus, um fortzufahren.")

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_online_api_filter():
    st.title("Online-API_Filter (Kombiniert)")
    st.write("Hier kombinierst du ggf. API-Auswahl und Online-Filter in einem Schritt.")
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_analyze_paper():
    st.title("Analyze Paper")
    st.write("Code für das Analysieren eines Papers. (Beispiel)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


###############################################################################
# 4) Sidebar Module Navigation & Main
###############################################################################

def sidebar_module_navigation():
    # Prüfen, ob der Login-Status existiert
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # Falls NICHT eingeloggt => Abbruch
    if not st.session_state["logged_in"]:
        return None

    # Eingeloggt => Navigation anzeigen
    st.sidebar.title("Modul-Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,
    }

    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    return pages[st.session_state["current_page"]]

def main():
    # Wenn wir keinen Login-Status haben, init
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # 1) Falls nicht eingeloggt => zeige Login
    if not st.session_state["logged_in"]:
        show_login()
        # Hier NICHT return, sondern st.stop(), damit kein weiterer Code kommt
        st.stop()

    # 2) Navigation
    page_fn = sidebar_module_navigation()
    # Falls None => st.stop()
    if page_fn is None:
        st.stop()

    # 3) Ausführen
    page_fn()


if __name__ == "__main__":
    main()
