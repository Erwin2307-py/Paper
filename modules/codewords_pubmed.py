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

# ----------------------------------------------------------------------------
# Versuche, scholarly und fpdf zu importieren
# ----------------------------------------------------------------------------
try:
    from scholarly import scholarly
except ImportError:
    st.error("Bitte installiere 'scholarly' (z.B. via: pip install scholarly)")
    st.stop()

try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf' (z.B. via: pip install fpdf)")
    st.stop()

# ----------------------------------------------------------------------------
# Patch für OpenAI-Fehlerklassen (einschließlich APIConnectionError)
# ----------------------------------------------------------------------------
def patch_openai_errors():
    error_names = [
        "AuthenticationError",
        "BadRequestError",
        "RateLimitError",
        "APIStatusError",
        "APITimeoutError",
        "APIConnectionError"
    ]
    for error_name in error_names:
        try:
            getattr(openai, error_name)
        except AttributeError:
            try:
                module = importlib.import_module("openai.error")
                setattr(openai, error_name, getattr(module, error_name))
            except (ImportError, AttributeError):
                st.warning(f"OpenAI-Fehlerklasse '{error_name}' wurde nicht gefunden. Dummy wird verwendet.")
                dummy_error = type(error_name, (Exception,), {})
                setattr(openai, error_name, dummy_error)

patch_openai_errors()

# ----------------------------------------------------------------------------
# Dummy-Modul für lmi erstellen (falls nicht vorhanden)
# ----------------------------------------------------------------------------
try:
    import lmi
except ImportError:
    st.warning("Modul 'lmi' nicht gefunden – Dummy-Implementierung wird verwendet.")
    dummy_lmi = types.ModuleType("lmi")
    
    # Dummy für LLMModel
    class LLMModel:
        def __init__(self, *args, **kwargs): pass
        def __call__(self, *args, **kwargs):
            return "Dummy LLMModel output"
    dummy_lmi.LLMModel = LLMModel

    # Dummy für EmbeddingModel
    class EmbeddingModel:
        def __init__(self, *args, **kwargs): pass
        def embed(self, text):
            return [0.0] * 768  # Beispielvektor
    dummy_lmi.EmbeddingModel = EmbeddingModel

    # Dummy für LiteLLMModel
    class LiteLLMModel(LLMModel): pass
    dummy_lmi.LiteLLMModel = LiteLLMModel

    # Dummy für LiteLLMEmbeddingModel
    class LiteLLMEmbeddingModel(EmbeddingModel): pass
    dummy_lmi.LiteLLMEmbeddingModel = LiteLLMEmbeddingModel

    # Dummy für HybridEmbeddingModel
    class HybridEmbeddingModel(EmbeddingModel): pass
    dummy_lmi.HybridEmbeddingModel = HybridEmbeddingModel

    # Dummy für SentenceTransformerEmbeddingModel
    class SentenceTransformerEmbeddingModel(EmbeddingModel): pass
    dummy_lmi.SentenceTransformerEmbeddingModel = SentenceTransformerEmbeddingModel

    # Dummy für SparseEmbeddingModel
    class SparseEmbeddingModel(EmbeddingModel): pass
    dummy_lmi.SparseEmbeddingModel = SparseEmbeddingModel

    # Dummy für LLMResult
    class LLMResult:
        def __init__(self, text=""):
            self.text = text
        def __str__(self):
            return self.text
    dummy_lmi.LLMResult = LLMResult

    # Dummy-Funktion für embedding_model_factory
    def embedding_model_factory(*args, **kwargs):
        return dummy_lmi.EmbeddingModel(*args, **kwargs)
    dummy_lmi.embedding_model_factory = embedding_model_factory

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
# Erwartete Repository-Struktur:
# your_repo/
# └── modules/
#     ├── codewords_pubmed.py   <-- Dieses Skript
#     └── paper-qa/
#          └── paper-qa-main/
#               └── paperqa/
#                    └── __init__.py
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
    Sucht in PubMed per ESearch + ESummary und gibt eine Liste einfacher Dicts zurück.
    """
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
    """
    Demonstriert PaperQA2: PDFs hochladen und eine Frage stellen.
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
# E) Haupt-App (Streamlit)
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
