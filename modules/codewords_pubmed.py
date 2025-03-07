import streamlit as st
import requests
import feedparser
import pandas as pd
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import base64
import importlib.util  # Für den dynamischen Import von PaperQA2

# ----------------------------------------------------------------------------
# Debug-Informationen
# ----------------------------------------------------------------------------
st.sidebar.markdown("**[DEBUG-INFO]**")
st.sidebar.code(f"""
Aktuelles Arbeitsverzeichnis: {os.getcwd()}
Systempfad (sys.path): {sys.path}
""")

# ----------------------------------------------------------------------------
# Wählen Sie die Import-Methode für PaperQA2
# ----------------------------------------------------------------------------
import_method = st.sidebar.radio(
    "Wählen Sie die Import-Methode für PaperQA2:",
    options=["Online (pip install paper-qa)", "Lokale Installation (dynamischer Import)"],
    index=0
)

Docs = None  # Platzhalter

if import_method == "Online (pip install paper-qa)":
    st.sidebar.info("Versuche, PaperQA2 online zu importieren (via 'from paperqa import Docs').")
    try:
        from paperqa import Docs as DocsOnline
        Docs = DocsOnline
    except ImportError as e:
        st.error("Fehler beim Online-Import von PaperQA2: " + str(e))
        st.stop()
else:
    st.sidebar.info("Versuche, PaperQA2 lokal dynamisch zu importieren.")
    # ----------------------------------------------------------------------------
    # A) Dynamischer Import von PaperQA2 via direktem Pfad zur __init__.py
    # ----------------------------------------------------------------------------
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    # Pfad anpassen – Hier wird angenommen, dass sich das Repository wie folgt strukturiert:
    # modules/
    #   ├── codewords_pubmed.py  (dieses Skript)
    #   └── paper-qa/
    #        └── paper-qa-main/
    #             └── paperqa/
    #                  └── __init__.py
    PAPERQA_INIT_FILE = os.path.join(
        CURRENT_DIR,
        "paper-qa",
        "paper-qa-main",
        "paperqa",
        "__init__.py"
    )
    if not os.path.isfile(PAPERQA_INIT_FILE):
        st.error(f"Kritischer Pfadfehler: {PAPERQA_INIT_FILE} existiert nicht!")
        st.stop()
    try:
        spec = importlib.util.spec_from_file_location("paperqa_custom", PAPERQA_INIT_FILE)
        paperqa_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(paperqa_module)
        if not hasattr(paperqa_module, "Docs"):
            st.error("Im dynamisch geladenen PaperQA2-Modul ist kein 'Docs' definiert!")
            st.stop()
        Docs = paperqa_module.Docs
    except Exception as e:
        st.error(f"Fehler beim Laden von PaperQA2 via {PAPERQA_INIT_FILE}: {e}")
        st.stop()

# ----------------------------------------------------------------------------
# B) Beispielhafte PubMed-Suchfunktion
# ----------------------------------------------------------------------------
def search_pubmed(query: str, max_results=100):
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    out = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return out

        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        summary_data = r2.json().get("result", {})

        for pmid in idlist:
            info = summary_data.get(pmid, {})
            title = info.get("title", "n/a")
            pubdate = info.get("pubdate", "n/a")
            year = pubdate[:4] if pubdate != "n/a" else "n/a"
            out.append({
                "Source": "PubMed",
                "Title": title,
                "PubMed ID": pmid,
                "Year": year
            })
        return out
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return out

# ----------------------------------------------------------------------------
# C) PaperQA2-Demo: PDFs hochladen und Frage stellen
# ----------------------------------------------------------------------------
def paperqa_test_locally():
    st.subheader("Lokaler PaperQA2-Test")
    docs = Docs()

    # PDFs hochladen
    pdfs = st.file_uploader("Lade PDF(s) hoch:", type=["pdf"], accept_multiple_files=True)
    if pdfs:
        for up in pdfs:
            pdf_bytes = up.read()
            try:
                docs.add(pdf_bytes, metadata=up.name)
                st.success(f"Datei '{up.name}' hinzugefügt.")
            except Exception as e:
                st.error(f"Fehler beim Hinzufügen von {up.name}: {e}")

    question = st.text_area("Frage an PaperQA2:")
    if st.button("PaperQA2-Abfrage starten"):
        if not question.strip():
            st.warning("Bitte eine Frage eingeben!")
        else:
            try:
                answer_obj = docs.query(question)
                st.markdown("### Antwort:")
                st.write(answer_obj.answer)
                with st.expander("Kontext / Belege"):
                    st.write(answer_obj.context)
            except Exception as e:
                st.error(f"Fehler bei PaperQA2-Abfrage: {e}")

# ----------------------------------------------------------------------------
# D) Haupt-Funktion (Streamlit-App)
# ----------------------------------------------------------------------------
def module_codewords_pubmed():
    st.title("Multi-API-Suche + PaperQA2 (lokaler Import)")
    
    # Beispiel: PubMed-Suche
    query = st.text_input("PubMed-Suchbegriff:", "Cancer")
    anzahl = st.number_input("Anzahl Treffer", min_value=1, max_value=200, value=10)
    if st.button("PubMed-Suche starten"):
        results = search_pubmed(query, max_results=anzahl)
        if results:
            st.write(f"{len(results)} PubMed-Ergebnisse gefunden:")
            df = pd.DataFrame(results)
            st.dataframe(df)
        else:
            st.info("Keine Treffer für PubMed.")

    st.write("---")
    st.subheader("PaperQA2 Test-Lauf (lokal)")
    paperqa_test_locally()


# ----------------------------------------------------------------------------
# Hauptprogramm
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide")
    st.title("Kombinierte App: Multi-API-Suche + PaperQA2 (Streamlit)")
    
    # Hier können Sie weitere Menüpunkte ergänzen
    menu = ["Home / Profile", "ChatGPT-Paper", "arXiv-Suche", "Multi-API-Suche + PaperQA2"]
    choice = st.sidebar.selectbox("Navigation", menu)
    
    if choice == "Multi-API-Suche + PaperQA2":
        module_codewords_pubmed()
    else:
        st.info("Bitte wählen Sie 'Multi-API-Suche + PaperQA2' aus dem Menü aus.")

if __name__ == "__main__":
    main()
