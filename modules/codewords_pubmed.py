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

# WICHTIG: Hier nehmen wir an, dass Ihr Pfad so aussieht:
#  Paper/modules/paper-qa/paper-qa-main/paperqa/__init__.py
#
#  ─ modules
#      ├─ codewords_pubmed.py  (dieses Skript)
#      └─ paper-qa
#         └─ paper-qa-main
#            └─ paperqa
#               └─ __init__.py

PAPERQA_INIT_FILE = os.path.join(
    CURRENT_DIR,            # => .../Paper/modules
    "paper-qa",            # 1. Ordner (Bindestrich)
    "paper-qa-main",       # 2. Ordner
    "paperqa",             # 3. Ordner (ohne Bindestrich)
    "__init__.py"          # Datei
)

# Pfadcheck
if not os.path.isfile(PAPERQA_INIT_FILE):
    st.error(f"Kritischer Pfadfehler: {PAPERQA_INIT_FILE} existiert nicht!")
    st.stop()

try:
    # Spec für das dynamische Laden
    spec = importlib.util.spec_from_file_location("paperqa_custom", PAPERQA_INIT_FILE)
    paperqa_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paperqa_module)

    # Prüfen, ob Docs vorhanden ist
    if not hasattr(paperqa_module, "Docs"):
        st.error("Im dynamisch geladenen PaperQA-Modul ist kein 'Docs' definiert!")
        st.stop()
except Exception as e:
    st.error(f"Fehler beim Laden von PaperQA via {PAPERQA_INIT_FILE}: {e}")
    st.stop()

# Jetzt haben wir paperqa_module mit paperqa_module.Docs
Docs = paperqa_module.Docs

# ----------------------------------------------------------------------------
# B) Ihre PubMed- (o. andere) Suchfunktionen
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

# ----------------------------------------------------------------------------
# C) PaperQA-Demo
# ----------------------------------------------------------------------------
def paperqa_test_locally():
    """
    Beispiel-Funktion, die PaperQA (Docs) nutzt, 
    um PDFs hochzuladen und eine Frage zu stellen.
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
# D) Haupt-Funktion (Streamlit)
# ----------------------------------------------------------------------------
def module_codewords_pubmed():
    """
    Diese Funktion enthält Ihre 'Multi-API-Suche' + PaperQA oder Codewords-Logik.
    Sie können sie in einer anderen Streamlit-App (z. B. main_app.py) aufrufen.
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

    # Anschließend PaperQA-Teil
    st.write("---")
    st.subheader("PaperQA Test-Lauf (lokal)")
    paperqa_test_locally()
