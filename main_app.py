import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime
import sys
import concurrent.futures
import os
import PyPDF2
import openai
import time
import json
import pdfplumber
import io

from typing import Dict, Any, Optional
from dotenv import load_dotenv
from PIL import Image
from scholarly import scholarly

from modules.online_api_filter import module_online_api_filter

# Neuer Import für die Übersetzung mit google_trans_new
from google_trans_new import google_translator

# ------------------------------------------------------------------
# Umgebungsvariablen laden (für OPENAI_API_KEY, falls vorhanden)
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------------------
# Streamlit-Konfiguration
# ------------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# ------------------------------------------------------------------
# Login-Funktionalität
# ------------------------------------------------------------------
def login():
    st.title("Login")
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if (
            user_input == st.secrets["login"]["username"]
            and pass_input == st.secrets["login"]["password"]
        ):
            st.session_state["logged_in"] = True
        else:
            st.error("Login failed. Please check your credentials!")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()

# ------------------------------------------------------------------
# 1) Gemeinsame Funktionen & Klassen
# ------------------------------------------------------------------

def clean_html_except_br(text):
    cleaned_text = re.sub(r'</?(?!br\b)[^>]*>', '', text)
    return cleaned_text

def translate_text_openai(text, source_language, target_language, api_key):
    """Übersetzt Text über OpenAI-ChatCompletion (z.B. GPT-4)"""
    import openai
    openai.api_key = api_key
    prompt_system = (
        f"You are a translation engine from {source_language} to {target_language} for a biotech company called Novogenia "
        f"that focuses on lifestyle and health genetics and health analyses. The outputs you provide will be used directly as "
        f"the translated text blocks. Please translate as accurately as possible in the context of health and lifestyle reporting. "
        f"If there is no appropriate translation, the output should be 'TBD'. Keep the TAGS and do not add additional punctuation."
    )
    prompt_user = f"Translate the following text from {source_language} to {target_language}:\n'{text}'"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # Falls Ihr Account dieses Modell unterstützt
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0
        )
        translation = response.choices[0].message.content.strip()
        if translation and translation[0] in ["'", '"', "‘", "„"]:
            translation = translation[1:]
            if translation and translation[-1] in ["'", '"']:
                translation = translation[:-1]
        translation = clean_html_except_br(translation)
        return translation
    except Exception as e:
        st.warning("Übersetzungsfehler: " + str(e))
        return text

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

# ------------------------------------------------------------------
# 2) PubMed - Einfacher Check + Search
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 3) Europe PMC Check + Search
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 4) OpenAlex API
# ------------------------------------------------------------------
BASE_URL = "https://api.openalex.org"

def fetch_openalex_data(entity_type, entity_id=None, params=None):
    url = f"{BASE_URL}/{entity_type}"
    if entity_id:
        url += f"/{entity_id}"
    if params is None:
        params = {}
    params["mailto"] = "your_email@example.com"
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

# ------------------------------------------------------------------
# 5) Google Scholar (Test)
# ------------------------------------------------------------------
class GoogleScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_google_scholar(self, base_query):
        try:
            search_results = scholarly.search_pubs(base_query)
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

# ------------------------------------------------------------------
# 6) Semantic Scholar
# ------------------------------------------------------------------
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
                    "DOI": "n/a",
                    "URL": url_article,
                    "Abstract": abstract_text
                })
        except Exception as e:
            st.error(f"Semantic Scholar: {e}")

# ------------------------------------------------------------------
# 7) Excel Online Search - Placeholder
# ------------------------------------------------------------------
# (Hier könnte Ihr Modul code stehen, falls benötigt)
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# 8) Weitere Module + Seiten
# ------------------------------------------------------------------
def module_paperqa2():
    st.subheader("PaperQA2 Module")
    st.write("Dies ist das PaperQA2 Modul. Hier kannst du weitere Einstellungen und Funktionen für PaperQA2 implementieren.")
    question = st.text_input("Bitte gib deine Frage ein:")
    if st.button("Frage absenden"):
        st.write("Antwort: Dies ist eine Dummy-Antwort auf die Frage:", question)

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
    st.title("PaperQA2")
    module_paperqa2()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_excel_online_search():
    st.title("Excel Online Search")
    from modules.online_api_filter import module_online_api_filter

def page_online_api_filter():
    st.title("Online-API_Filter (Kombiniert)")
    st.write("Hier kombinierst du ggf. API-Auswahl und Online-Filter in einem Schritt.")
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

# ------------------------------------------------------------------
# 9) PAPER ANALYZER + Klasse PaperAnalyzer
# ------------------------------------------------------------------
class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model
    
    def extract_text_from_pdf(self, pdf_file):
        """Extrahiert reinen Text via PyPDF2 (ggf. OCR nötig, falls PDF nicht durchsuchbar)."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    
    def analyze_with_openai(self, text, prompt_template, api_key):
        """Allgemeine Hilfsfunktion, um Text an OpenAI-ChatCompletion zu schicken."""
        if len(text) > 15000:
            text = text[:15000] + "..."
        prompt = prompt_template.format(text=text)
        openai.api_key = api_key
        response = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": (
                    "Du bist ein Experte für die Analyse wissenschaftlicher Paper, "
                    "besonders im Bereich Side-Channel Analysis."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content
    
    def summarize(self, text, api_key):
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere sie in mindestens vier klar getrennte Abschnitte "
            "(z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
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
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf "
            f"einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

# ------------------------------------------------------------------
# 10) Neue Klasse AlleleFrequencyFinder
# ------------------------------------------------------------------
class AlleleFrequencyFinder:
    """Klasse zum Abrufen und Anzeigen von Allelfrequenzen aus verschiedenen Quellen."""
    def __init__(self):
        self.ensembl_server = "https://rest.ensembl.org"
        self.max_retries = 3
        self.retry_delay = 2  # Sekunden zwischen Wiederholungsversuchen

    def get_allele_frequencies(self, rs_id: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        if not rs_id.startswith("rs"):
            rs_id = f"rs{rs_id}"
        endpoint = f"/variation/human/{rs_id}?pops=1"
        url = f"{self.ensembl_server}{endpoint}"
        try:
            response = requests.get(url, headers={"Content-Type": "application/json"}, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            if response.status_code == 500 and retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self.get_allele_frequencies(rs_id, retry_count + 1)
            elif response.status_code == 404:
                return None
            else:
                return None
        except requests.exceptions.RequestException:
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self.get_allele_frequencies(rs_id, retry_count + 1)
            return None
    
    def try_alternative_source(self, rs_id: str) -> Optional[Dict[str, Any]]:
        """Platzhalter: alternativer Weg, falls Ensembl down ist."""
        return None
    
    def parse_and_display_data(self, data: Dict[str, Any]) -> None:
        if not data:
            print("Keine Daten verfügbar.")
            return
        print(json.dumps(data, indent=2))
    
    def build_freq_info_text(self, data: Dict[str, Any]) -> str:
        if not data:
            return "Keine Daten von Ensembl"
        maf = data.get("MAF", None)
        pops = data.get("populations", [])
        out = []
        out.append(f"MAF={maf}" if maf else "MAF=n/a")
        if pops:
            max_pop = 2
            for i, pop in enumerate(pops):
                if i >= max_pop:
                    break
                pop_name = pop.get('population', 'N/A')
                allele = pop.get('allele', 'N/A')
                freq = pop.get('frequency', 'N/A')
                out.append(f"{pop_name}:{allele}={freq}")
        else:
            out.append("Keine Populationsdaten gefunden.")
        return " | ".join(out)

# ------------------------------------------------------------------
# 11) Hilfsfunktionen
# ------------------------------------------------------------------
def split_summary(summary_text):
    m = re.search(r'Ergebnisse\s*:\s*(.*?)\s*Schlussfolgerungen\s*:\s*(.*)', summary_text, re.DOTALL | re.IGNORECASE)
    if m:
        ergebnisse = m.group(1).strip()
        schlussfolgerungen = m.group(2).strip()
    else:
        ergebnisse = summary_text
        schlussfolgerungen = ""
    return ergebnisse, schlussfolgerungen

def parse_cohort_info(summary_text: str) -> dict:
    """
    Sucht nach Studiengröße & Herkunft. Enthält alte + neue Logik:
      - z.B. "693 Filipino children and adolescents"
      - z.B. "130 Patienten / 130 gesunde Kontrollpersonen"
    """
    info = {"study_size": "", "origin": ""}

    # Neue Logik: "(xxx) (Filipino|Chinese|...) (children|adolescents|...)"
    pattern_nationality = re.compile(
        r"(\d+)\s+(Filipino|Chinese|Japanese|Han\sChinese|[A-Za-z]+)\s+([Cc]hildren(?:\s+and\s+adolescents)?|adolescents?|participants?|subjects?)",
        re.IGNORECASE
    )
    match_nat = pattern_nationality.search(summary_text)
    if match_nat:
        num_str = match_nat.group(1)
        origin_str = match_nat.group(2)
        group_str = match_nat.group(3)
        info["study_size"] = f"{num_str} {group_str}"
        info["origin"] = origin_str

    # Alte Logik
    pattern_both = re.compile(
        r"(\d+)\s*Patient(?:en)?(?:[^\d]+)(\d+)\s*gesunde\s*Kontroll(?:personen)?",
        re.IGNORECASE
    )
    m_both = pattern_both.search(summary_text)
    if m_both and not info["study_size"]:
        p_count = m_both.group(1)
        c_count = m_both.group(2)
        info["study_size"] = f"{p_count} Patienten / {c_count} Kontrollpersonen"
    else:
        pattern_single_p = re.compile(r"(\d+)\s*Patient(?:en)?", re.IGNORECASE)
        m_single_p = pattern_single_p.search(summary_text)
        if m_single_p and not info["study_size"]:
            info["study_size"] = f"{m_single_p.group(1)} Patienten"

    # Herkunft / Population: "in der xyz Bevölkerung"
    pattern_origin = re.compile(r"in\s*der\s+(\S+)\s+Bevölkerung", re.IGNORECASE)
    m_orig = pattern_origin.search(summary_text)
    if m_orig and not info["origin"]:
        info["origin"] = m_orig.group(1).strip()

    return info

# ------------------------------------------------------------------
# 12) PAGE "Analyze Paper" (inkl. 5. Analyseart: Tabellen & Grafiken)
# ------------------------------------------------------------------
def page_analyze_paper():
    st.title("Analyze Paper - Integriert")
    
    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""
    
    st.sidebar.header("Einstellungen - PaperAnalyzer")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value
    
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    
    # NEU: 5. Eintrag "Tabellen & Grafiken"
    action = st.sidebar.radio(
        "Analyseart",
        [
            "Zusammenfassung", 
            "Wichtigste Erkenntnisse", 
            "Methoden & Techniken", 
            "Relevanz-Bewertung",
            "Tabellen & Grafiken"  # <-- NEU
        ],
        index=0
    )
    
    topic = st.sidebar.text_input("Thema für Relevanz-Bewertung (falls relevant)")
    output_lang = st.sidebar.selectbox(
        "Ausgabesprache",
        ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"],
        index=0
    )
    
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]
    
    # ---------- EINZEL-ANALYSE ----------
    if uploaded_file and api_key:
        if st.button("Analyse starten"):
            # (A) Falls NICHT "Tabellen & Grafiken", extrahieren wir klassisch den Text
            text = ""
            if action != "Tabellen & Grafiken":
                with st.spinner("Extrahiere Text aus PDF..."):
                    text = analyzer.extract_text_from_pdf(uploaded_file)
                    if not text.strip():
                        st.error("Kein Text extrahierbar (evtl. PDF ohne OCR).")
                        st.stop()
                    st.success("Text wurde erfolgreich extrahiert!")
                    st.session_state["paper_text"] = text[:15000]

            # (B) Abhängig vom gewählten Modus
            if action == "Zusammenfassung":
                with st.spinner("Erstelle Zusammenfassung..."):
                    result = analyzer.summarize(text, api_key)

            elif action == "Wichtigste Erkenntnisse":
                with st.spinner("Extrahiere wichtigste Erkenntnisse..."):
                    result = analyzer.extract_key_findings(text, api_key)

            elif action == "Methoden & Techniken":
                with st.spinner("Identifiziere Methoden & Techniken..."):
                    result = analyzer.identify_methods(text, api_key)

            elif action == "Relevanz-Bewertung":
                if not topic:
                    st.error("Bitte Thema angeben für die Relevanz-Bewertung!")
                    st.stop()
                with st.spinner("Bewerte Relevanz..."):
                    result = analyzer.evaluate_relevance(text, topic, api_key)

            # NEU: Tabellen & Grafiken
            elif action == "Tabellen & Grafiken":
                with st.spinner("Suche nach Tabellen und Grafiken..."):
                    all_tables_text = []
                    try:
                        with pdfplumber.open(uploaded_file) as pdf:
                            for page_number, page in enumerate(pdf.pages, start=1):
                                st.markdown(f"### Seite {page_number}")
                                
                                # ----- Tabellen extrahieren -----
                                tables = page.extract_tables()
                                if tables:
                                    st.markdown("**Tabellen auf dieser Seite**")
                                    for table_idx, table in enumerate(tables, start=1):
                                        df = pd.DataFrame(table[1:], columns=table[0])
                                        st.write(f"**Tabelle {table_idx}**:")
                                        st.dataframe(df)
                                        # Für GPT: Wir verwandeln die Tabelle in reinen Text
                                        table_str = df.to_csv(index=False)
                                        # Wir speichern sie in "all_tables_text" ab
                                        all_tables_text.append(f"Seite {page_number} - Tabelle {table_idx}\n{table_str}\n")
                                else:
                                    st.write("Keine Tabellen auf dieser Seite gefunden.")
                                
                                # ----- Bilder extrahieren -----
                                images = page.images
                                if images:
                                    st.markdown("**Bilder/Grafiken auf dieser Seite**")
                                    for img_index, img_dict in enumerate(images, start=1):
                                        # KORREKTES Extrahieren via xref:
                                        xref = img_dict.get("xref")
                                        if xref is not None:
                                            extracted_img = page.extract_image(xref)
                                            if extracted_img:
                                                image_data = extracted_img["image"]
                                                image = Image.open(io.BytesIO(image_data))
                                                st.write(f"**Bild {img_index}**:")
                                                st.image(image, use_column_width=True)
                                            else:
                                                st.write(f"Bild {img_index} konnte nicht extrahiert werden.")
                                else:
                                    st.write("Keine Bilder auf dieser Seite gefunden.")
                    
                    except Exception as e:
                        st.error(f"Fehler beim Auslesen von Tabellen/Bildern: {str(e)}")
                        result = "(Keine Auswertung möglich)"
                    else:
                        # Wenn wir mindestens eine Tabelle haben, lassen wir GPT analysieren
                        if len(all_tables_text) > 0:
                            # Wir limitieren ggf. die Länge des Textes
                            combined_tables_text = "\n".join(all_tables_text)
                            if len(combined_tables_text) > 14000:
                                combined_tables_text = combined_tables_text[:14000] + "..."
                            
                            # Kurze Auswertung
                            gpt_prompt = (
                                "Bitte analysiere die folgenden Tabellen aus einem wissenschaftlichen PDF. "
                                "Fasse die wichtigsten Erkenntnisse zusammen und gib (wenn möglich) eine "
                                "kurze Interpretation in Bezug auf Lifestyle und Health Genetics:\n\n"
                                f"{combined_tables_text}"
                            )
                            with st.spinner("GPT analysiert Tabellen..."):
                                openai.api_key = api_key
                                try:
                                    gpt_resp = openai.chat.completions.create(
                                        model=model,
                                        messages=[
                                            {"role": "system", "content": "Du bist ein Experte für PDF-Tabellenanalyse."},
                                            {"role": "user", "content": gpt_prompt}
                                        ],
                                        temperature=0.3,
                                        max_tokens=1000
                                    )
                                    result = gpt_resp.choices[0].message.content
                                except Exception as e2:
                                    st.error(f"Fehler bei GPT-Auswertung der Tabellen: {str(e2)}")
                                    result = "(Fehler bei GPT-Auswertung)"
                        else:
                            result = "Keine Tabellen gefunden, daher keine Auswertung."

            # Ausgabe: Optionale Übersetzung
            if action != "Tabellen & Grafiken":
                # Bei den ersten 4 Analysearten haben wir 'result' direkt. 
                # Bei "Tabellen & Grafiken" kommt result erst unten.
                if output_lang != "Deutsch" and (action != "Tabellen & Grafiken"):
                    lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                    target_lang = lang_map.get(output_lang, "English")
                    result = translate_text_openai(result, "German", target_lang, api_key)
            
            # Falls wir nach "Tabellen & Grafiken" das Ergebnis noch übersetzen wollen:
            if action == "Tabellen & Grafiken" and result and output_lang != "Deutsch":
                lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                target_lang = lang_map.get(output_lang, "English")
                result = translate_text_openai(result, "German", target_lang, api_key)

            # Finale Ausgabe
            st.subheader("Ergebnis der Analyse:")
            st.markdown(result)
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_file:
            st.info("Bitte eine PDF-Datei hochladen!")
    
    # ----------- GESAMT-WORKFLOW + Excel-Ausgabe (optional) -----------
    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe")
    user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")
    
    if uploaded_file and api_key:
        if st.button("Alle Analysen durchführen & in Excel speichern"):
            with st.spinner("Analysiere alles..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Kein Text extrahierbar (evtl. PDF ohne OCR).")
                    st.stop()
    
                # (1) Zusammenfassung & Key Findings
                summary_result = analyzer.summarize(text, api_key)
                key_findings_result = analyzer.extract_key_findings(text, api_key)
                methods_result = analyzer.identify_methods(text, api_key)
                if not topic:
                    st.error("Bitte 'Thema für Relevanz-Bewertung' angeben!")
                    st.stop()
                relevance_result = analyzer.evaluate_relevance(text, topic, api_key)
                final_relevance = f"{relevance_result}\n\n[Manuelle Bewertung: {user_relevance_score}]"
    
                import openpyxl
                import datetime
    
                # (2) Excel-Vorlage laden
                try:
                    wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                except FileNotFoundError:
                    st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                    st.stop()
                ws = wb.active
    
                # (3) Gene-Detection
                pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                match_text = re.search(pattern_obvious, text)
                gene_via_text = match_text.group(1) if match_text else None

                if gene_via_text:
                    found_gene = gene_via_text
                else:
                    # Falls wir in vorlage_gene.xlsx nach möglichen Genen suchen wollen
                    try:
                        wb_gene = openpyxl.load_workbook("vorlage_gene.xlsx")
                    except FileNotFoundError:
                        st.error("Die Datei 'vorlage_gene.xlsx' wurde nicht gefunden!")
                        st.stop()
    
                    ws_gene = wb_gene.active
                    gene_names_from_excel = []
                    for row in ws_gene.iter_rows(min_row=3, min_col=3, max_col=3, values_only=True):
                        cell_value = row[0]
                        if cell_value and isinstance(cell_value, str):
                            gene_names_from_excel.append(cell_value.strip())
    
                    found_gene = None
                    for g in gene_names_from_excel:
                        pat = re.compile(r"\b" + re.escape(g) + r"\b", re.IGNORECASE)
                        if re.search(pat, text):
                            found_gene = g
                            break
    
                # (4) rsID / Allele Frequencies
                if found_gene:
                    ws["D5"] = found_gene
    
                rs_pat = r"(rs\d+)"
                found_rs = re.search(rs_pat, text)
                rs_num = None
                if found_rs:
                    rs_num = found_rs.group(1)
                    ws["D6"] = rs_num
    
                genotype_regex = r"\b([ACGT]{2,3})\b"
                lines = text.split("\n")
                found_pairs = []
                for line in lines:
                    matches = re.findall(genotype_regex, line)
                    if matches:
                        for m in matches:
                            found_pairs.append((m, line.strip()))
    
                unique_geno_pairs = []
                for gp in found_pairs:
                    if gp not in unique_geno_pairs:
                        unique_geno_pairs.append(gp)
    
                aff = AlleleFrequencyFinder()
                if rs_num:
                    data = aff.get_allele_frequencies(rs_num)
                    if not data:
                        data = aff.try_alternative_source(rs_num)
                    if data:
                        freq_info = aff.build_freq_info_text(data)
                    else:
                        freq_info = "Keine Daten von Ensembl/dbSNP"
                else:
                    freq_info = "Keine rsID vorhanden"
    
                if len(unique_geno_pairs) > 0:
                    ws["D10"] = unique_geno_pairs[0][0]
                    ws["F10"] = unique_geno_pairs[0][1]
                    ws["E10"] = freq_info
    
                if len(unique_geno_pairs) > 1:
                    ws["D11"] = unique_geno_pairs[1][0]
                    ws["F11"] = unique_geno_pairs[1][1]
                    ws["E11"] = freq_info
    
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ws["J2"] = now_str
    
                # (5) Ergebnisse / Schlussfolgerungen => G21 / G22 (in Englisch)
                ergebnisse, schlussfolgerungen = split_summary(summary_result)
                eng_ergebnisse = translate_text_openai(ergebnisse, "German", "English", api_key)
                eng_schlussfolgerungen = translate_text_openai(schlussfolgerungen, "German", "English", api_key)
                ws["G21"] = eng_ergebnisse
                ws["G22"] = eng_schlussfolgerungen
    
                # (6) Studiengröße & Herkunft => D20, Key Findings => E20
                #    => Alles in Englisch
                cohort_data = parse_cohort_info(summary_result)
                study_size = cohort_data.get("study_size", "")
                origin = cohort_data.get("origin", "")
                combined_str = f"Study Size: {study_size} | Ethnicity: {origin}"
    
                # Übersetzen (falls nötig)
                if combined_str.strip() and (not re.search(r"[a-zA-Z]", combined_str) or "Patienten" in combined_str):
                    # Nur wenn da noch Deutsch drin sein könnte
                    combined_str = translate_text_openai(combined_str, "German", "English", api_key)
                
                ws["D20"] = combined_str  # D20 => study size & origin in English
                
                # Key Findings => E20 (englisch)
                key_findings_en = translate_text_openai(key_findings_result, "German", "English", api_key)
                ws["E20"] = key_findings_en
    
                # (7) Excel speichern
                output_buffer = io.BytesIO()
                wb.save(output_buffer)
                output_buffer.seek(0)
    
            st.success("Alle Analysen abgeschlossen – Excel-Datei erstellt und Felder befüllt!")
            st.download_button(
                label="Download Excel",
                data=output_buffer,
                file_name="analysis_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# ------------------------------------------------------------------
# 13) Sidebar & Chatbot
# ------------------------------------------------------------------
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    return pages.get(st.session_state["current_page"], page_home)

def answer_chat(question: str) -> str:
    """Einfaches Beispiel: Nutzt Paper-Text (falls vorhanden) aus st.session_state + GPT."""
    api_key = st.session_state.get("api_key", "")
    paper_text = st.session_state.get("paper_text", "")
    if not api_key:
        return f"(Kein API-Key) Echo: {question}"
    
    if not paper_text.strip():
        sys_msg = "Du bist ein hilfreicher Assistent für allgemeine Fragen."
    else:
        sys_msg = (
            "Du bist ein hilfreicher Assistent, und hier ist ein Paper als Kontext:\n\n"
            + paper_text[:12000] + "\n\n"
            "Bitte nutze es, um Fragen möglichst fachkundig zu beantworten."
        )
    
    openai.api_key = api_key
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=400
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"OpenAI-Fehler: {e}"

# ------------------------------------------------------------------
# 14) Hauptfunktion (Startpunkt)
# ------------------------------------------------------------------
def main():
    # CSS-Anpassungen für das scrollbare Chat-Fenster
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        .scrollable-chat {
            max-height: 400px; /* feste oder maximale Höhe */
            overflow-y: scroll; /* scrollbar wenn zu lang */
            border: 1px solid #CCC;
            padding: 8px;
            margin-top: 10px;
            border-radius: 4px;
            background-color: #f9f9f9;
        }
        
        /* Nachrichten-Styling */
        .message {
            padding: 0.5rem 1rem;
            border-radius: 15px;
            margin-bottom: 0.5rem;
            max-width: 80%;
            word-wrap: break-word;
        }
        .user-message {
            background-color: #e3f2fd;
            margin-left: auto;
            border-bottom-right-radius: 0;
        }
        .assistant-message {
            background-color: #f0f0f0;
            margin-right: auto;
            border-bottom-left-radius: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    col_left, col_right = st.columns([4, 1])
    with col_left:
        page_fn = sidebar_module_navigation()
        if page_fn is not None:
            page_fn()

    with col_right:
        st.subheader("Chatbot")

        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        user_input = st.text_input("Deine Frage hier", key="chatbot_right_input")
        if st.button("Absenden (Chat)", key="chatbot_right_send"):
            if user_input.strip():
                st.session_state["chat_history"].append(("user", user_input))
                bot_answer = answer_chat(user_input)
                st.session_state["chat_history"].append(("bot", bot_answer))

        # Chatverlauf in scrollbarem Container anzeigen
        st.markdown('<div class="scrollable-chat" id="chat-container">', unsafe_allow_html=True)
        for role, msg_text in st.session_state["chat_history"]:
            if role == "user":
                st.markdown(
                    f'<div class="message user-message"><strong>Du:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="message assistant-message"><strong>Bot:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
        st.markdown('</div>', unsafe_allow_html=True)

        # JavaScript, um automatisch nach unten zu scrollen
        st.markdown(
            """
            <script>
                // Funktion zum automatischen Scrollen
                function scrollToBottom() {
                    var container = document.getElementById('chat-container');
                    if(container) {
                        container.scrollTop = container.scrollHeight;
                    }
                }
                
                // Scrollen nach dem Laden der Seite
                document.addEventListener('DOMContentLoaded', function() {
                    scrollToBottom();
                });
                
                // Beobachter, der auf Veränderungen im Chat-Container reagiert
                const observer = new MutationObserver(function(mutations) {
                    scrollToBottom();
                });
                
                // Sobald der Container existiert, wird der Observer gestartet
                setTimeout(function() {
                    var container = document.getElementById('chat-container');
                    if(container) {
                        observer.observe(container, { childList: true });
                        scrollToBottom();
                    }
                }, 1000);
            </script>
            """,
            unsafe_allow_html=True
        )

# ------------------------------------------------------------------
# Skriptstart
# ------------------------------------------------------------------
if __name__ == '__main__':
    main()
