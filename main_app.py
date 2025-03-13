import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

from modules.online_api_filter import module_online_api_filter  # Falls noch benötigt

# ------------------------------------------------------------
# EINMALIGE set_page_config(...) hier ganz am Anfang aufrufen
# ------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

################################################################################
# 0) LOGIN-FUNKTION
################################################################################

def show_login():
    """Zeigt das Login-Formular und das Willkommensbild an."""
    st.title("Bitte zuerst einloggen")
    st.image("Bild1.jpg", caption="Willkommen!", use_container_width=False, width=600)

    user = st.text_input("Benutzername:")
    pw = st.text_input("Passwort:", type="password")

    if st.button("Einloggen"):
        # Beispielhaftes Checken der Zugangsdaten
        if user == "demo" and pw == "secret":
            st.session_state["logged_in"] = True
            st.success("Erfolgreich eingeloggt! Wähle nun im Seitenmenü eine Funktion.")
        else:
            st.error("Falsche Anmeldedaten. Bitte erneut versuchen.")


################################################################################
# 1) Gemeinsame Funktionen & Klassen
################################################################################

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


################################################################################
# (PubMed-Funktionen, EuropePMC, OpenAlex usw. bleiben unverändert)
# ... Code analog deinem Beispiel ...
################################################################################

################################################################################
# 3) Pages
################################################################################

def module_paperqa2():
    st.subheader("PaperQA2 Module")
    st.write("Dies ist das PaperQA2 Modul. Hier kannst du weitere Einstellungen "
             "und Funktionen für PaperQA2 implementieren.")
    question = st.text_input("Bitte gib deine Frage ein:")
    if st.button("Frage absenden"):
        st.write("Antwort: Dies ist eine Dummy-Antwort auf die Frage:", question)

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

# Beispiel: "Analyze Paper" Seite
def page_analyze_paper():
    st.title("Analyze Paper")
    st.write("Füge hier deinen Code für das Analysieren eines Papers ein, "
             "oder integriere den Code aus 'analyze_paper.py' direkt.")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

################################################################################
# 4) Sidebar Module Navigation & Main
################################################################################

def sidebar_module_navigation():
    # Falls wir noch keinen Login-Status haben, definieren wir ihn hier.
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # Falls NICHT eingeloggt => kein Seitenmenü anzeigen
    if not st.session_state["logged_in"]:
        return None  # Damit man im main() merkt: Keine "richtige" Seite gewählt

    # Wenn eingeloggt, normales Seitenmenü
    st.sidebar.title("Modul-Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,
        # Weitere Seite-Funktionen hier ...
    }

    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    return pages.get(st.session_state["current_page"], page_home)

def main():
    # -------------------------
    # 1) LOGIN PRÜFEN
    # -------------------------
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        # Wenn nicht eingeloggt: Zeige das Login
        show_login()
        return  # Danach Abbruch => Login-Seite bleibt stehen

    # -------------------------
    # 2) NAVIGATION
    # -------------------------
    page_fn = sidebar_module_navigation()
    if page_fn is None:
        # Falls noch keine Seite
        st.stop()

    # -------------------------
    # 3) GEWÄHLTE SEITE AUSFÜHREN
    # -------------------------
    page_fn()


if __name__ == '__main__':
    main()
