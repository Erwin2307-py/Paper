import sys
import types
import importlib.util
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
import openai

# Versuche zuerst, das Modul lmi zu importieren. Falls nicht vorhanden, erstelle ein Dummy-Modul.
try:
    import lmi
except ImportError:
    dummy_lmi = types.ModuleType("lmi")
    
    class EmbeddingModel:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, text):
            # Gibt einen Dummy-Vektor zurück
            return [0.0] * 768

    dummy_lmi.EmbeddingModel = EmbeddingModel

    class HybridEmbeddingModel(EmbeddingModel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    dummy_lmi.HybridEmbeddingModel = HybridEmbeddingModel

    # Dummy-Klasse für LiteLLMEmbeddingModel
    class LiteLLMEmbeddingModel(EmbeddingModel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    dummy_lmi.LiteLLMEmbeddingModel = LiteLLMEmbeddingModel

    # Falls PaperQA2 auch LiteLLMModel benötigt:
    class LiteLLMModel(EmbeddingModel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    dummy_lmi.LiteLLMModel = LiteLLMModel

    sys.modules["lmi"] = dummy_lmi

# ----------------------------------------------------------------------------
# Debug-Informationen (zur Überprüfung in Streamlit Cloud)
# ----------------------------------------------------------------------------
st.sidebar.markdown("**[DEBUG-INFO]**")
st.sidebar.code(f"""
Aktuelles Arbeitsverzeichnis: {os.getcwd()}
Systempfad (sys.path): {sys.path}
""")

# ----------------------------------------------------------------------------
# A) Dynamischer Import von PaperQA2 via direktem Pfad zur __init__.py
# ----------------------------------------------------------------------------
# Annahme: Ihre Repository-Struktur sieht so aus:
# your_repo/
# └── modules/
#     ├── codewords_pubmed.py   <-- Dieses Skript
#     └── paper-qa/
#          └── paper-qa-main/
#               └── paperqa/
#                    └── __init__.py
#
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

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
except Exception as e:
    st.error(f"Fehler beim Laden von PaperQA2 via {PAPERQA_INIT_FILE}: {e}")
    st.stop()

Docs = paperqa_module.Docs

# ----------------------------------------------------------------------------
# B) Beispielhafte Such-Funktion für PubMed
# ----------------------------------------------------------------------------
def search_pubmed(query: str, max_results=100):
    """
    Sucht in PubMed per ESearch und ESummary.
    Gibt eine Liste von Dicts mit Title, PubMed-ID und Jahr zurück.
    """
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }
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
    """
    Ermöglicht das Hochladen von PDF-Dateien und das Stellen einer Frage
    an das PaperQA2-System über die Docs-Klasse.
    """
    st.subheader("Lokaler PaperQA2-Test")
    docs = Docs()

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
# D) Multi-API-Suche + PaperQA2-Demo (Beispiel: PubMed-Suche + PaperQA2)
# ----------------------------------------------------------------------------
def module_codewords_pubmed():
    st.title("Multi-API-Suche + PaperQA2 (lokaler Import)")

    query = st.text_input("PubMed-Suchbegriff:", "Cancer")
    anzahl = st.number_input("Anzahl Treffer", min_value=1, max_value=200, value=10)
    if st.button("PubMed-Suche starten"):
        results = search_pubmed(query, max_results=anzahl)
        if results:
            st.write(f"{len(results)} Ergebnisse via PubMed:")
            df = pd.DataFrame(results)
            st.dataframe(df)
        else:
            st.info("Keine Treffer für PubMed.")

    st.write("---")
    st.subheader("PaperQA2 Test-Lauf (lokal)")
    paperqa_test_locally()

# ----------------------------------------------------------------------------
# E) Hauptprogramm (Streamlit-App)
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide")
    st.title("Kombinierte App: Multi-API-Suche + PaperQA2 (Streamlit)")
    menu = ["Multi-API-Suche + PaperQA2"]
    choice = st.sidebar.selectbox("Navigation", menu)
    if choice == "Multi-API-Suche + PaperQA2":
        module_codewords_pubmed()
    else:
        st.info("Bitte wählen Sie eine Option aus dem Menü.")

if __name__ == "__main__":
    main()
