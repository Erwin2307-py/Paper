import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

from modules.online_api_filter import module_online_api_filter

# Nur einmal das Layout setzen
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# ----------------------------------------------------------------
# LOGIN-LOGIK MIT SECRETS
# ----------------------------------------------------------------

def show_login():
    """
    Zeigt ein Login-Formular mit Bild. Holt Benutzername/Passwort 
    aus st.secrets["login"]["username"] / ["login"]["password"].
    """
    st.title("Bitte zuerst einloggen")
    st.image("Bild1.jpg", caption="Willkommen!", use_container_width=False, width=600)

    # Secrets: Username und Passwort aus secrets.toml
    SECRET_USER = st.secrets["login"]["username"]
    SECRET_PASS = st.secrets["login"]["password"]

    user = st.text_input("Benutzername:")
    pw = st.text_input("Passwort:", type="password")

    if st.button("Einloggen"):
        if user == SECRET_USER and pw == SECRET_PASS:
            st.session_state["logged_in"] = True
            st.success("Erfolgreich eingeloggt! Wähle nun ein Modul in der Sidebar.")
        else:
            st.error("Falsche Login-Daten. Bitte erneut versuchen.")

# ----------------------------------------------------------------
# 1) Gemeinsame Funktionen & Klassen
# ----------------------------------------------------------------

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

# (PubMed, EuropePMC, usw. bleiben unverändert – abgekürzt)
# ...

# ----------------------------------------------------------------
# 2) Pages
# ----------------------------------------------------------------

def module_paperqa2():
    st.subheader("PaperQA2 Module")
    st.write("Dies ist das PaperQA2 Modul. Hier kannst du weitere Einstellungen und Funktionen für PaperQA2 implementieren.")
    question = st.text_input("Bitte gib deine Frage ein:")
    if st.button("Frage absenden"):
        st.write("Antwort: Dies ist eine Dummy-Antwort auf die Frage:", question)

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Du bist erfolgreich eingeloggt! Wähle ein Modul in der Sidebar aus, um fortzufahren.")
    st.image("Bild1.jpg", caption="Willkommen!", width=600)

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

# ----------------------------------------------------------------
# 3) Analyze Paper (integriert, wie in deinem Code)
# ----------------------------------------------------------------

import os
import PyPDF2
import openai
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model
    
    def extract_text_from_pdf(self, pdf_file):
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        if len(text) > 15000:
            text = text[:15000] + "..."

        prompt = prompt_template.format(text=text)
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Experte für die Analyse wissenschaftlicher Paper, "
                        "besonders im Bereich Side-Channel Analysis."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def summarize(self, text, api_key):
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere es in: Hintergrund, Methodik, "
            "Ergebnisse und Schlussfolgerungen. Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text, api_key):
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen "
            "Paper im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text, api_key):
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text, topic, api_key):
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' "
            f"auf einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

def page_analyze_paper():
    st.title("Analyze Paper - Integriert")

    # Sidebar-Einstellungen für Analyzer
    st.sidebar.header("Einstellungen - PaperAnalyzer")
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    model = st.sidebar.selectbox("OpenAI-Modell",
                                 ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
                                 index=0)
    action = st.sidebar.radio("Analyseart",
                              ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
                              index=0)
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")

    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    analyzer = PaperAnalyzer(model=model)

    if uploaded_file and api_key:
        if st.button("Analyse starten"):
            with st.spinner("Extrahiere Text aus PDF..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Kein Text extrahierbar (evtl. nur gescanntes PDF ohne OCR).")
                    st.stop()
                st.success("Text wurde erfolgreich extrahiert!")

            with st.spinner(f"Führe {action}-Analyse durch..."):
                if action == "Zusammenfassung":
                    result = analyzer.summarize(text, api_key)
                elif action == "Wichtigste Erkenntnisse":
                    result = analyzer.extract_key_findings(text, api_key)
                elif action == "Methoden & Techniken":
                    result = analyzer.identify_methods(text, api_key)
                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Bitte Thema angeben für die Relevanz-Bewertung!")
                        st.stop()
                    result = analyzer.evaluate_relevance(text, topic, api_key)

                st.subheader("Ergebnis der Analyse")
                st.markdown(result)
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_file:
            st.info("Bitte eine PDF-Datei hochladen!")

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

# ----------------------------------------------------------------
# 4) LOGIN + NAVIGATION
# ----------------------------------------------------------------

def sidebar_module_navigation():
    """
    Erzeugt das Seiten-Menü. Wird nur angezeigt, wenn login OK.
    """
    st.sidebar.title("Modul-Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,
        # ggf. weitere
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]

def show_app():
    """Zeigt das Hauptprogramm (Navigation + aktive Seite)."""
    page_fn = sidebar_module_navigation()
    page_fn()


def main():
    # 1) Login-Status initialisieren
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # 2) Wenn noch NICHT eingeloggt => Login anzeigen, Rest ausblenden
    if not st.session_state["logged_in"]:
        show_login()
        return  # Abbruch => es wird nur die Login-Seite gerendert

    # 3) Angemeldet => App zeigen
    show_app()

if __name__ == "__main__":
    main()
