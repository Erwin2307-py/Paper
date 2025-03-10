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
import sys
import importlib.util

# ------------------------ Streamlit Cloud-Spezifische Einstellungen ------------------------
# Pfad zur PaperQA Installation im Repository
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERQA_PATH = os.path.join(CURRENT_DIR, "modules", "paper-qa")

# Systempfad anpassen
if PAPERQA_PATH not in sys.path:
    sys.path.insert(0, PAPERQA_PATH)

# ------------------------ PaperQA Import mit Fehlerdiagnose ------------------------
try:
    from paperqa import Docs
except ImportError as e:
    st.error(f"""
    Kritischer Importfehler: {e}
    Bitte überprüfe:
    1. Existiert der Ordner '{PAPERQA_PATH}'?
    2. Enthält er die Datei '__init__.py'?
    3. Ist das Repository als Submodule integriert?
    """)
    st.stop()

# ------------------------ API-Schlüssel Management ------------------------
# OpenAI-Key aus Streamlit Secrets
if "OPENAI_API_KEY" not in st.secrets:
    st.error("OPENAI_API_KEY fehlt in Streamlit Secrets!")
    st.stop()

os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

# ------------------------ Hauptfunktionen ------------------------
def search_pubmed(query: str, max_results=100):
    """PubMed-Suche über NCBI eUtils"""
    try:
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        
        if not idlist:
            return []
        
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        
        return process_pubmed_results(r2.json())
    
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def process_pubmed_results(data):
    """Verarbeitet PubMed-Ergebnisse"""
    results = []
    summary_data = data.get("result", {})
    
    for pmid in summary_data.get("uids", []):
        info = summary_data.get(pmid, {})
        results.append({
            "Title": info.get("title", "n/a"),
            "Authors": ", ".join(info.get("authors", [])[:3]),
            "Journal": info.get("source", "n/a"),
            "Year": info.get("pubdate", "n/a")[:4] if "pubdate" in info else "n/a",
            "PMID": pmid
        })
    
    return results

# ------------------------ PaperQA Integration ------------------------
def paperqa_query_interface():
    """UI für PaperQA-Abfragen"""
    st.subheader("PaperQA Dokumentenanalyse")
    
    # Dokumenten-Upload
    uploaded_files = st.file_uploader(
        "PDF-Dokumente hochladen",
        type=["pdf"],
        accept_multiple_files=True
    )
    
    # PaperQA-Docs initialisieren
    docs = Docs()
    
    # Dokumente verarbeiten
    if uploaded_files:
        for file in uploaded_files:
            try:
                docs.add(file.read(), metadata=file.name)
                st.success(f"{file.name} erfolgreich hinzugefügt")
            except Exception as e:
                st.error(f"Fehler bei {file.name}: {str(e)}")
    
    # Frage-Eingabe
    question = st.text_area("Stellen Sie eine Frage zu den Dokumenten:")
    
    if st.button("Analyse starten") and question:
        with st.spinner("Analysiere Dokumente..."):
            try:
                answer = docs.query(question)
                display_results(answer)
            except Exception as e:
                st.error(f"Analysefehler: {str(e)}")

def display_results(answer):
    """Zeigt PaperQA-Ergebnisse an"""
    st.subheader("Ergebnis")
    st.markdown(f"**Antwort:** {answer.answer}")
    
    with st.expander("Detailierte Belege"):
        st.markdown(answer.context)
    
    with st.expander("Zitationsanalyse"):
        for evidence in answer.docs:
            st.markdown(f"""
            **Dokument:** {evidence.metadata.get('name', 'Unbekannt')}
            **Relevanz:** {evidence.score:.2f}
            **Inhalt:** {evidence.text[:300]}...
            """)

# ------------------------ Hauptanwendung ------------------------
def main():
    st.set_page_config(
        page_title="Wissenschaftliche Analyseplattform",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🔬 Wissenschaftliche Analyseplattform")
    
    menu_options = {
        "PubMed-Suche": pubmed_search,
        "Dokumentenanalyse": paperqa_query_interface
    }
    
    choice = st.sidebar.selectbox("Menü", list(menu_options.keys()))
    
    # Debug-Info
    st.sidebar.markdown("### Systeminformationen")
    st.sidebar.code(f"""
    Python-Pfad: {sys.path}
    Arbeitsverzeichnis: {os.getcwd()}
    PaperQA-Pfad: {PAPERQA_PATH}
    """)
    
    menu_options[choice]()

def pubmed_search():
    """UI für PubMed-Suche"""
    st.subheader("PubMed Literatursuche")
    query = st.text_input("Suchbegriff(e)", "machine learning cancer")
    max_results = st.number_input("Maximale Treffer", 1, 500, 50)
    
    if st.button("Suche starten"):
        results = search_pubmed(query, max_results)
        
        if results:
            df = pd.DataFrame(results)
            st.dataframe(
                df[["Title", "Authors", "Year", "PMID"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("Keine Treffer gefunden")

if __name__ == "__main__":
    main()
