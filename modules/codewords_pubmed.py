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
import importlib.util  # <--- für den dynamischen Import von paperqa

# ----------------------------------------------------------------------------
# A) Dynamischer Import von PaperQA via direktem Pfad zur __init__.py
# ----------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Pfad: "paper-qa/paperqa/__init__.py" liegt auf derselben Ebene wie `codewords_pubmed.py`
# also: Paper/modules/paper-qa/paperqa/__init__.py
PAPERQA_INIT_FILE = os.path.join(
    CURRENT_DIR,          # => .../Paper/modules
    "paper-qa",           # Ordner (mit Bindestrich)
    "paperqa",            # Ordner (ohne Bindestrich)
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
        st.error("Im dynamisch geladenen PaperQA-Modul ist kein 'Docs' definiert!")
        st.stop()
except Exception as e:
    st.error(f"Fehler beim Laden von PaperQA via {PAPERQA_INIT_FILE}: {e}")
    st.stop()

# Jetzt haben wir paperqa_module mit paperqa_module.Docs
Docs = paperqa_module.Docs

# ----------------------------------------------------------------------------
# B) Weitere (vorhandene) Funktionen für Such-APIs etc.
# (PubMed, Europe PMC, Google Scholar, ...) – ggf. anpassen oder kürzen
# ----------------------------------------------------------------------------

def search_pubmed(query: str, max_results=100):
    """Kürzliches Beispiel: Sucht in PubMed per ESearch + ESummary."""
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
            year = info.get("pubdate", "n/a")[:4]
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

def search_google_scholar(query: str, max_results=10):
    """Dummy-Funktion, wenn 'scholarly' installiert ist."""
    results = []
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs(query)
        for i, pub in enumerate(search_results):
            if i >= max_results:
                break
            bib = pub.get("bib", {})
            title = bib.get("title", "n/a")
            year = bib.get("pub_year", "n/a")
            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "Year": year
            })
        return results
    except Exception as e:
        st.error(f"Google Scholar-Suche fehlgeschlagen: {e}")
        return []

# ----------------------------------------------------------------------------
# C) PaperQA-Logik: z. B. Abfrage
# ----------------------------------------------------------------------------
def paperqa_test_locally():
    """
    Beispiel-Funktion, die PaperQA (Docs) nutzt, um PDFs hochzuladen
    und eine Frage zu stellen.
    """
    st.subheader("Lokaler PaperQA-Test via codewords_pubmed")
    docs = Docs()

    # PDF hochladen
    pdfs = st.file_uploader("Lade PDF(s) hoch:", type=["pdf"], accept_multiple_files=True)
    if pdfs:
        for up in pdfs:
            pdf_bytes = up.read()
            try:
                docs.add(pdf_bytes, metadata=up.name)
                st.success(f"Datei '{up.name}' hinzugefügt.")
            except Exception as e:
                st.error(f"Fehler beim Hinzufügen von {up.name}: {e}")

    question = st.text_area("Frage eingeben (PaperQA):")
    if st.button("PaperQA-Abfrage starten"):
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
                st.error(f"Fehler bei PaperQA-Abfrage: {e}")

# ----------------------------------------------------------------------------
# D) Haupt-Funktion, die man in 'main_app.py' oder in Streamlit direkt aufruft
# ----------------------------------------------------------------------------
def module_codewords_pubmed():
    """
    Diese Funktion enthält weiterhin Ihre 'Multi-API-Suche' + PaperQA oder Codewords-Logik.
    Sie kann von main_app.py importiert und aufgerufen werden.
    """
    st.title("Multi-API-Suche + PaperQA (lokaler Import)")

    # Beispiel: Benutzer kann Suchbegriff eingeben
    query = st.text_input("Suchbegriff:", "Cancer")
    if st.button("PubMed-Suche starten"):
        res = search_pubmed(query)
        if res:
            st.write(f"{len(res)} Ergebnisse via PubMed:")
            df = pd.DataFrame(res)
            st.dataframe(df)

    # Beispiel: PaperQA-Teil
    st.write("---")
    st.subheader("PaperQA Test-Lauf (lokal)")
    paperqa_test_locally()
