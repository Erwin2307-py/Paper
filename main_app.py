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
import importlib.util
import sys

# ----------------------------------------------------------------------------
# Debug-Informationen (zur Überprüfung in Streamlit Cloud)
# ----------------------------------------------------------------------------
st.sidebar.markdown("**[DEBUG-INFO]**")
st.sidebar.code(f"""
Aktuelles Arbeitsverzeichnis: {os.getcwd()}
Systempfad (sys.path): {sys.path}
""")

# ----------------------------------------------------------------------------
# Beispielhafte Funktionen (z. B. CoreAPI, PubMed, Europe PMC, OpenAlex, Google Scholar)
# ----------------------------------------------------------------------------

class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=100):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = [f"{k}:{v}" for k, v in filters.items()]
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort
        r = requests.get(self.base_url + endpoint, headers=self.headers, params=params, timeout=15)
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
        for item in raw.get("results", []):
            out.append({
                "PMID": "n/a",
                "Title": item.get("title", "n/a"),
                "Year": str(item.get("yearPublished", "n/a")),
                "Journal": item.get("publisher", "n/a")
            })
        return out
    except Exception as e:
        st.error(f"CORE search error: {e}")
        return []

def check_pubmed_connection(timeout=10):
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def search_pubmed_simple(query):
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
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
            out.append({
                "PMID": pmid,
                "Title": info.get("title", "n/a"),
                "Year": info.get("pubdate", "n/a")[:4],
                "Journal": info.get("fulljournalname", "n/a")
            })
        return out
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

def fetch_pubmed_abstract(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = [elem.text.strip() for elem in root.findall(".//AbstractText") if elem.text]
        return "\n".join(abs_text) if abs_text else "(No abstract available)"
    except Exception as e:
        return f"(Error: {e})"

def search_europe_pmc_simple(query):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 100, "resultType": "core"}
    out = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("resultList", {}).get("result", [])
        for item in results:
            out.append({
                "PMID": item.get("pmid", "n/a"),
                "Title": item.get("title", "n/a"),
                "Year": str(item.get("pubYear", "n/a")),
                "Journal": item.get("journalTitle", "n/a")
            })
        return out
    except Exception as e:
        st.error(f"Europe PMC search error: {e}")
        return []

def fetch_openalex_data(entity_type, entity_id=None, params=None):
    url = f"https://api.openalex.org/{entity_type}"
    if entity_id:
        url += f"/{entity_id}"
    if params is None:
        params = {}
    params["mailto"] = "your_email@example.com"  # Bitte ersetzen Sie diese E-Mail-Adresse
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Fehler: {response.status_code} - {response.text}")
        return None

def search_openalex_simple(query):
    search_params = {"search": query}
    return fetch_openalex_data("works", params=search_params)

# ----------------------------------------------------------------------------
# D) Dynamischer Import von PaperQA2 (als separates Modul)
# ----------------------------------------------------------------------------
def load_paperqa2_module():
    """
    Lädt das PaperQA2-Modul dynamisch. Wir gehen davon aus, dass sich PaperQA2 in
    modules/paper-qa/paper-qa-main/paperqa/__init__.py befindet.
    """
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
        return paperqa_module
    except Exception as e:
        st.error(f"Fehler beim Laden von PaperQA2 via {PAPERQA_INIT_FILE}: {e}")
        st.stop()

# ----------------------------------------------------------------------------
# E) PaperQA2-Demo: PDFs hochladen und Frage stellen
# ----------------------------------------------------------------------------
def paperqa_test_locally():
    """
    Demonstriert PaperQA2: PDFs hochladen und eine Frage stellen.
    """
    st.subheader("Lokaler PaperQA2-Test")
    paperqa_module = load_paperqa2_module()
    Docs = paperqa_module.Docs
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
# F) Multi-API-Suche + PaperQA2-Demo (Beispiel)
# ----------------------------------------------------------------------------
def module_codewords_pubmed():
    st.title("Multi-API-Suche + PaperQA2 (lokaler Import)")
    
    # Beispiel: PubMed-Suche
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
# G) Haupt-App (Streamlit)
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

if __name__ == '__main__':
    main()
