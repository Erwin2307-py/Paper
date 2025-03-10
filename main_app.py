import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

# Neu hinzugefügte Imports für PaperQA2 / Haystack / OpenAI
import openai
import pdfplumber
from haystack.document_stores import FAISSDocumentStore
from haystack.nodes import EmbeddingRetriever
from haystack import Document
import tempfile
import os

# Remove or comment out the direct module_online_filter import if you no longer need it here:
# from modules.online_filter import module_online_filter

# ENTFERNT: Hier importieren wir dein Selenium-Modul aus modules/
# from modules import my_selenium_qa_module

# NEW: We import the combined “online API + filter” module
from modules.online_api_filter import module_online_api_filter  # <-- CHANGED HERE

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

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
# PubMed Connection Check + (Basis) Search
################################################################################

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
    """Kurze Version: Sucht nur, ohne Abstract / Details."""
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
            title = info.get("title", "n/a")
            pubdate = info.get("pubdate", "")
            year = pubdate[:4] if pubdate else "n/a"
            journal = info.get("fulljournalname", "n/a")
            out.append({
                "PMID": pmid,
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []


def fetch_pubmed_abstract(pmid):
    """Holt den Abstract via efetch für eine gegebene PubMed-ID."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = []
        for elem in root.findall(".//AbstractText"):
            if elem.text:
                abs_text.append(elem.text.strip())
        if abs_text:
            return "\n".join(abs_text)
        else:
            return "(No abstract available)"
    except Exception as e:
        return f"(Error: {e})"


################################################################################
# Europe PMC Connection Check + (Basis) Search
################################################################################

def check_europe_pmc_connection(timeout=10):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False


def search_europe_pmc_simple(query):
    """Kurze Version: Sucht nur, ohne erweiterte Details."""
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": 100,
        "resultType": "core"
    }
    out = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "resultList" not in data or "result" not in data["resultList"]:
            return out
        results = data["resultList"]["result"]
        for item in results:
            pmid = item.get("pmid", "n/a")
            title = item.get("title", "n/a")
            year = str(item.get("pubYear", "n/a"))
            journal = item.get("journalTitle", "n/a")
            out.append({
                "PMID": pmid if pmid else "n/a",
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"Europe PMC search error: {e}")
        return []


################################################################################
# OpenAlex API Communication
################################################################################

BASE_URL = "https://api.openalex.org"

def fetch_openalex_data(entity_type, entity_id=None, params=None):
    url = f"{BASE_URL}/{entity_type}"
    if entity_id:
        url += f"/{entity_id}"
    if params is None:
        params = {}
    params["mailto"] = "your_email@example.com"  # Ersetze durch deine E-Mail-Adresse
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Fehler: {response.status_code} - {response.text}")
        return None

def search_openalex_simple(query):
    """Kurze Version: Liest die rohen Daten, prüft nur, ob was zurückkommt."""
    search_params = {"search": query}
    return fetch_openalex_data("works", params=search_params)


################################################################################
# Google Scholar (Basis) Test
################################################################################

from scholarly import scholarly

class GoogleScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_google_scholar(self, base_query):
        try:
            search_results = scholarly.search_pubs(base_query)
            # Nur 5 Abrufe als Test
            for _ in range(5):
                result = next(search_results)
                title = result['bib'].get('title', "n/a")
                authors = result['bib'].get('author', "n/a")
                year = result['bib'].get('pub_year', "n/a")
                url_article = result.get('url_scholarbib', "n/a")
                abstract_text = result['bib'].get('abstract', "")
                self.all_results.append({
                    "Source": "Google Scholar",
                    "Title": title,
                    "Authors/Description": authors,
                    "Journal/Organism": "n/a",
                    "Year": year,
                    "PMID": "n/a",
                    "DOI": "n/a",
                    "URL": url_article,
                    "Abstract": abstract_text
                })
        except Exception as e:
            st.error(f"Fehler bei der Google Scholar-Suche: {e}")


################################################################################
# Semantic Scholar API Communication
################################################################################

def check_semantic_scholar_connection(timeout=10):
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": "test", "limit": 1, "fields": "title"}
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.status_code == 200
    except Exception:
        return False


class SemanticScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_semantic_scholar(self, base_query):
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
            params = {"query": base_query, "limit": 5, "fields": "title,authors,year,abstract,doi,paperId"}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            for paper in data.get("data", []):
                title = paper.get("title", "n/a")
                authors = ", ".join([author.get("name", "") for author in paper.get("authors", [])])
                year = paper.get("year", "n/a")
                doi = paper.get("doi", "n/a")
                paper_id = paper.get("paperId", "")
                abstract_text = paper.get("abstract", "")
                url_article = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "n/a"
                self.all_results.append({
                    "Source": "Semantic Scholar",
                    "Title": title,
                    "Authors/Description": authors,
                    "Journal/Organism": "n/a",
                    "Year": year,
                    "PMID": "n/a",
                    "DOI": doi,
                    "URL": url_article,
                    "Abstract": abstract_text
                })
        except Exception as e:
            st.error(f"Semantic Scholar: {e}")


################################################################################
# 2) Neues Modul: "module_excel_online_search"
################################################################################
# [unverändert, Belassen Sie hier, falls alles korrekt läuft...]


################################################################################
# 3) Restliche Module + Seiten (Pages)
################################################################################

# ============================================================================
# Neue PaperQA2-Logik
# ============================================================================

def module_paperqa2():
    # OpenAI-API-Key setzen (entweder aus Streamlit-Secrets oder Umgebungsvariable)
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else os.getenv("OPENAI_API_KEY")
    openai.api_key = OPENAI_API_KEY

    # FAISS-Dokument-Store zur Vektorsuche initialisieren (einmal pro Session)
    if "document_store" not in st.session_state:
        st.session_state.document_store = FAISSDocumentStore(embedding_dim=768)

    if "retriever" not in st.session_state:
        st.session_state.retriever = EmbeddingRetriever(
            document_store=st.session_state.document_store,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            model_format="sentence_transformers"
        )

    def process_pdf(uploaded_file):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(uploaded_file.read())
            temp_filename = temp_file.name

        # PDF auslesen
        text_chunks = []
        with pdfplumber.open(temp_filename) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Beispielhafter Split nach Doppel-Absätzen
                    text_chunks.extend(text.split("\n\n"))

        # Als Haystack-Dokumente speichern
        docs = [Document(content=chunk) for chunk in text_chunks]
        st.session_state.document_store.write_documents(docs)
        st.session_state.document_store.update_embeddings(st.session_state.retriever)

        # Temporäre Datei löschen
        os.remove(temp_filename)
        st.success(f"PDF '{uploaded_file.name}' wurde erfolgreich verarbeitet und indexiert!")

    # ---------------- UI -------------------
    st.title("📄 PaperQA2: Wissenschaftliche Q&A basierend auf Paper-Daten")
    st.write("Lade wissenschaftliche PDFs hoch, stelle Fragen und erhalte fundierte Antworten.")

    uploaded_file = st.file_uploader("📥 Lade ein PDF hoch", type=["pdf"])
    if uploaded_file:
        process_pdf(uploaded_file)

    st.divider()

    question = st.text_input("🔎 Ihre Frage an das Paper:")
    num_matches = st.slider("🔢 Anzahl der relevanten Passagen", 1, 5, 3)

    if st.button("💡 PaperQA2 starten"):
        if not question:
            st.warning("⚠ Bitte geben Sie eine Frage ein.")
        else:
            # Dokumente abrufen
            results = st.session_state.retriever.retrieve(question, top_k=num_matches)

            # Kontext zusammensetzen
            context_text = ""
            for idx, doc in enumerate(results):
                context_text += f"Abschnitt {idx+1}:\n{doc.content}\n\n"

            # Prompt für OpenAI
            prompt = (
                f"Lies die folgenden wissenschaftlichen Paper-Auszüge und beantworte anschließend die Frage.\n\n"
                f"{context_text}"
                f"Frage: {question}\nAntwort:"
            )

            try:
                # OpenAI-Aufruf
                response = openai.Completion.create(
                    engine="text-davinci-003",  # oder "gpt-3.5-turbo"
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=300,
                    n=1
                )
                answer = response['choices'][0]['text'].strip()

                # Ausgabe
                st.write("### ✅ Antwort:")
                st.write(answer)

                with st.expander("📜 Genutzte Kontextstellen"):
                    for doc in results:
                        st.markdown(f"**Ähnlichkeits-Score {doc.score:.2f}:**\n\n{doc.content[:300]}…")

            except Exception as e:
                st.error(f"Fehler bei OpenAI-API: {e}")

    st.divider()

    if st.button("🗑 Datenbank zurücksetzen"):
        st.session_state.document_store.delete_documents()
        st.success("🗃 FAISS-Datenbank wurde zurückgesetzt.")


def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.image("Bild1.jpg", caption="Willkommen!", use_container_width=False, width=600)


def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_paper_selection():
    st.title("Paper Selection Settings")
    st.write("Define how you want to pick or exclude certain papers. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_analysis():
    st.title("Analysis & Evaluation Settings")
    st.write("Set up your analysis parameters, thresholds, etc. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_extended_topics():
    st.title("Extended Topics")
    st.write("Access advanced or extended topics for further research. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_paperqa2():
    # Du kannst das hier ggf. auskommentieren, um den Doppel-Titel zu vermeiden:
    st.title("PaperQA2")
    module_paperqa2()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_excel_online_search():
    st.title("Excel Online Search")
    from modules.online_api_filter import module_online_api_filter
    # Rufe hier dein Modul auf oder führe sonstige Logik aus
    # ...


# 4) Selenium Q&A: auskommentiert, um Fehler zu verhindern
# def page_selenium_qa():
#     st.title("Selenium Q&A (Modul) - Example")
#     st.write("Dies ruft das Modul 'my_selenium_qa_module' auf.")
#     # ...
#     if st.button("Back to Main Menu"):
#         st.session_state["current_page"] = "Home"


def page_online_api_filter():
    st.title("Online-API_Filter (Kombiniert)")
    st.write("Hier kombinierst du ggf. API-Auswahl und Online-Filter in einem Schritt.")
    module_online_api_filter()  # This function is presumably the combined logic
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


################################################################################
# 6) Sidebar Module Navigation & Main
################################################################################

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        # "1) API Selection": page_api_selection,     # <-- REMOVED
        # "2) Online Filter": page_online_filter,     # <-- REMOVED
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics,
        "7) PaperQA2": page_paperqa2,
        "8) Excel Online Search": page_excel_online_search
        # "9) Selenium Q&A": page_selenium_qa,       # <-- auskommentiert
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]


def main():
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    page_fn = sidebar_module_navigation()
    page_fn()


if __name__ == '__main__':
    main()
