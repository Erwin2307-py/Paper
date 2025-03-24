import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
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
import zipfile

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
    openai.api_key = api_key
    prompt_system = (
        f"You are a translation engine from {source_language} to {target_language} for a biotech company called Novogenia "
        f"that focuses on lifestyle and health genetics and health analyses. The outputs you provide will be used directly as "
        f"the translated text blocks. Please translate as accurately as possible in the context of health and lifestyle reporting. "
        f"If there is no appropriate translation, the output should be 'TBD'. Keep the TAGS and do not add additional punctuation."
    )
    prompt_user = f"Translate the following text from {source_language} to {target_language}:\n'{text}'"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # oder ein anderes Modell, falls unterstützt
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
        return clean_html_except_br(translation)
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

# ------------------------------------------------------------------
# 2) PubMed - Einfacher Check + Search
# ------------------------------------------------------------------
def check_pubmed_connection(timeout=10):
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        return "esearchresult" in r.json()
    except Exception:
        return False

def search_pubmed_simple(query):
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
    out = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        idlist = r.json().get("esearchresult", {}).get("idlist", [])
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
                "Year": info.get("pubdate", "")[:4] if info.get("pubdate") else "n/a",
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
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 100, "resultType": "core"}
    out = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
        for item in results:
            out.append({
                "PMID": item.get("pmid", "n/a") or "n/a",
                "Title": item.get("title", "n/a"),
                "Year": str(item.get("pubYear", "n/a")),
                "Journal": item.get("journalTitle", "n/a")
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
                self.all_results.append({
                    "Source": "Google Scholar",
                    "Title": result['bib'].get('title', "n/a"),
                    "Authors/Description": result['bib'].get('author', "n/a"),
                    "Journal/Organism": "n/a",
                    "Year": result['bib'].get('pub_year', "n/a"),
                    "PMID": "n/a",
                    "DOI": "n/a",
                    "URL": result.get('url_scholarbib', "n/a"),
                    "Abstract": result['bib'].get('abstract', "")
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
            for paper in response.json().get("data", []):
                self.all_results.append({
                    "Source": "Semantic Scholar",
                    "Title": paper.get("title", "n/a"),
                    "Authors/Description": ", ".join([author.get("name", "") for author in paper.get("authors", [])]),
                    "Journal/Organism": "n/a",
                    "Year": paper.get("year", "n/a"),
                    "PMID": "n/a",
                    "DOI": paper.get("doi", "n/a"),
                    "URL": f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}" if paper.get("paperId") else "n/a",
                    "Abstract": paper.get("abstract", "")
                })
        except Exception as e:
            st.error(f"Semantic Scholar: {e}")

# ------------------------------------------------------------------
# 7) Excel Online Search - Placeholder
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
        openai.api_key = api_key
        # Verwende den neuen API-Aufruf (keine alten client-Aufrufe)
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": (
                    "Du bist ein Experte für die Analyse wissenschaftlicher Paper, besonders im Bereich Side-Channel Analysis."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content
    def summarize(self, text, api_key):
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden wissenschaftlichen Papers. "
            "Gliedere sie in mindestens vier klar getrennte Abschnitte (z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    def extract_key_findings(self, text, api_key):
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper im Bereich Side-Channel Analysis. "
            "Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    def identify_methods(self, text, api_key):
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden und Techniken zur Side-Channel-Analyse. "
            "Gib zu jeder Methode eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    def evaluate_relevance(self, text, topic, api_key):
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf einer Skala von 1-10. "
            f"Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

class AlleleFrequencyFinder:
    def __init__(self):
        self.ensembl_server = "https://rest.ensembl.org"
        self.max_retries = 3
        self.retry_delay = 2
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
        out = [f"MAF={maf}" if maf else "MAF=n/a"]
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

def split_summary(summary_text):
    m = re.search(r'Ergebnisse\s*:\s*(.*?)\s*Schlussfolgerungen\s*:\s*(.*)', summary_text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    else:
        return summary_text.strip(), ""

def parse_cohort_info(summary_text: str) -> dict:
    info = {"study_size": "", "origin": ""}
    pattern_nationality = re.compile(
        r"(\d+)\s+(Filipino|Chinese|Japanese|Han\sChinese|[A-Za-z]+)\s+([Cc]hildren(?:\s+and\s+adolescents)?|adolescents?|participants?|subjects?)",
        re.IGNORECASE
    )
    match_nat = pattern_nationality.search(summary_text)
    if match_nat:
        info["study_size"] = f"{match_nat.group(1)} {match_nat.group(3)}"
        info["origin"] = match_nat.group(2)
    pattern_both = re.compile(
        r"(\d+)\s*Patient(?:en)?(?:[^\d]+)(\d+)\s*gesunde\s*Kontroll(?:personen)?",
        re.IGNORECASE
    )
    m_both = pattern_both.search(summary_text)
    if m_both and not info["study_size"]:
        info["study_size"] = f"{m_both.group(1)} Patienten / {m_both.group(2)} Kontrollpersonen"
    else:
        pattern_single_p = re.compile(r"(\d+)\s*Patient(?:en)?", re.IGNORECASE)
        m_single_p = pattern_single_p.search(summary_text)
        if m_single_p and not info["study_size"]:
            info["study_size"] = f"{m_single_p.group(1)} Patienten"
    pattern_origin = re.compile(r"in\s*der\s+(\S+)\s+Bevölkerung", re.IGNORECASE)
    m_orig = pattern_origin.search(summary_text)
    if m_orig and not info["origin"]:
        info["origin"] = m_orig.group(1).strip()
    return info

def page_analyze_paper():
    st.title("Analyze Paper - Integriert")
    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""
    st.sidebar.header("Einstellungen - PaperAnalyzer")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value
    model = st.sidebar.selectbox("OpenAI-Modell", ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"], index=0)
    compare_mode = st.sidebar.checkbox("Alle Paper gemeinsam vergleichen (Outlier ausschließen)?")
    theme_mode = st.sidebar.radio("Hauptthema bestimmen", ["Manuell", "GPT"])
    action = st.sidebar.radio("Analyseart",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung", "Tabellen & Grafiken"],
        index=0)
    user_defined_theme = ""
    if theme_mode == "Manuell":
        user_defined_theme = st.sidebar.text_input("Manuelles Hauptthema (bei Compare-Mode)")
    topic = st.sidebar.text_input("Thema für Relevanz-Bewertung (falls relevant)")
    output_lang = st.sidebar.selectbox("Ausgabesprache", ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"], index=0)
    uploaded_files = st.file_uploader("PDF-Dateien hochladen", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]
    if "relevant_papers_compare" not in st.session_state:
        st.session_state["relevant_papers_compare"] = None
    if "theme_compare" not in st.session_state:
        st.session_state["theme_compare"] = ""
    
    def do_outlier_logic(paper_map: dict) -> (list, str):
        if theme_mode == "Manuell":
            main_theme = user_defined_theme.strip()
            if not main_theme:
                st.error("Bitte ein manuelles Hauptthema eingeben!")
                return ([], "")
            snippet_list = []
            for name, txt_data in paper_map.items():
                snippet = txt_data[:700].replace("\n"," ")
                snippet_list.append(f'{{"filename": "{name}", "snippet": "{snippet}"}}')
            big_snippet = ",\n".join(snippet_list)
            big_input = f"""
Der Nutzer hat folgendes Hauptthema definiert: '{main_theme}'.

Hier sind mehrere Paper in JSON-Form. Entscheide pro Paper, ob es zu diesem Thema passt oder nicht.
Gib mir am Ende ein JSON-Format zurück:

{{
  "theme": "du wiederholst das user-defined theme",
  "papers": [
    {{"filename": "...", "relevant": true/false, "reason": "Kurzer Grund"}}
  ]
}}

Nur das JSON, ohne weitere Erklärungen.

[{big_snippet}]
"""
            try:
                openai.api_key = api_key
                scope_resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Du checkst Paper-Snippets auf Relevanz zum user-Thema."},
                        {"role": "user", "content": big_input}
                    ],
                    temperature=0.0,
                    max_tokens=1800
                )
                scope_decision = scope_resp.choices[0].message.content
            except Exception as e1:
                st.error(f"GPT-Fehler bei Compare-Mode (Manuell): {e1}")
                return ([], "")
            st.markdown("#### GPT-Ausgabe (Outlier-Check / Manuell):")
            st.code(scope_decision, language="json")
            json_str = scope_decision.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"```[\w]*\n?", "", json_str)
                json_str = re.sub(r"\n?```", "", json_str)
            try:
                data_parsed = json.loads(json_str)
                papers_info = data_parsed.get("papers", [])
            except Exception as parse_e:
                st.error(f"Fehler beim JSON-Parsing: {parse_e}")
                return ([], "")
            st.write(f"**Hauptthema (Manuell)**: {main_theme}")
            relevant_papers_local = []
            st.write("**Paper-Einstufung**:")
            for p in papers_info:
                fname = p.get("filename","?")
                if p.get("relevant", False):
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Begründung: {p.get('reason','(none)')}")
                else:
                    st.warning(f"{fname} => NICHT relevant. Begründung: {p.get('reason','(none)')}")
            return (relevant_papers_local, main_theme)
        else:
            snippet_list = []
            for name, txt_data in paper_map.items():
                snippet = txt_data[:700].replace("\n"," ")
                snippet_list.append(f'{{"filename": "{name}", "snippet": "{snippet}"}}')
            big_snippet = ",\n".join(snippet_list)
            big_input = f"""
Hier sind mehrere Paper in JSON-Form. Bitte ermittele das gemeinsame Hauptthema.
Dann antworte mir in folgendem JSON-Format: 
{{
  "main_theme": "Kurzbeschreibung des gemeinsamen Themas",
  "papers": [
    {{"filename": "...", "relevant": true/false, "reason": "Kurzer Grund"}}
  ]
}}

Bitte NUR dieses JSON liefern, ohne weitere Erklärungen:

[{big_snippet}]
"""
            try:
                openai.api_key = api_key
                scope_resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Du bist ein Assistent, der Paper thematisch filtert."},
                        {"role": "user", "content": big_input}
                    ],
                    temperature=0.0,
                    max_tokens=1800
                )
                scope_decision = scope_resp.choices[0].message.content
            except Exception as e1:
                st.error(f"GPT-Fehler bei Compare-Mode: {e1}")
                return ([], "")
            st.markdown("#### GPT-Ausgabe (Outlier-Check / GPT):")
            st.code(scope_decision, language="json")
            json_str = scope_decision.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"```[\w]*\n?", "", json_str)
                json_str = re.sub(r"\n?```", "", json_str)
            try:
                data_parsed = json.loads(json_str)
                main_theme = data_parsed.get("main_theme", "No theme extracted.")
                papers_info = data_parsed.get("papers", [])
            except Exception as parse_e:
                st.error(f"Fehler beim JSON-Parsing: {parse_e}")
                return ([], "")
            st.write(f"**Hauptthema (GPT)**: {main_theme}")
            relevant_papers_local = []
            st.write("**Paper-Einstufung**:")
            for p in papers_info:
                fname = p.get("filename","?")
                if p.get("relevant", False):
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Begründung: {p.get('reason','(none)')}")
                else:
                    st.warning(f"{fname} => NICHT relevant. Begründung: {p.get('reason','(none)')}")
            return (relevant_papers_local, main_theme)
    
    # Haupt-Analyse-Bereich
    if uploaded_files and api_key:
        if compare_mode:
            st.write("### Vergleichsmodus: Outlier-Paper ausschließen")
            if st.button("Vergleichs-Analyse starten"):
                paper_map = {}
                for fpdf in uploaded_files:
                    txt = analyzer.extract_text_from_pdf(fpdf)
                    if txt.strip():
                        paper_map[fpdf.name] = txt
                    else:
                        st.warning(f"Kein Text aus {fpdf.name} extrahierbar (übersprungen).")
                if not paper_map:
                    st.error("Keine verwertbaren Paper.")
                    return
                relevant_papers, discovered_theme = do_outlier_logic(paper_map)
                st.session_state["relevant_papers_compare"] = relevant_papers
                st.session_state["theme_compare"] = discovered_theme
                if not relevant_papers:
                    st.error("Keine relevanten Paper nach Outlier-Check übrig.")
                    return
                combined_text = ""
                for rp in relevant_papers:
                    combined_text += f"\n=== {rp} ===\n{paper_map[rp]}"
                if action == "Tabellen & Grafiken":
                    final_result = "Tabellen & Grafiken nicht im kombinierten Compare-Mode implementiert."
                else:
                    if action == "Zusammenfassung":
                        final_result = analyzer.summarize(combined_text, api_key)
                    elif action == "Wichtigste Erkenntnisse":
                        final_result = analyzer.extract_key_findings(combined_text, api_key)
                    elif action == "Methoden & Techniken":
                        final_result = analyzer.identify_methods(combined_text, api_key)
                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Bitte Thema angeben!")
                            return
                        final_result = analyzer.evaluate_relevance(combined_text, topic, api_key)
                    else:
                        final_result = "(Keine Analyseart gewählt.)"
                if output_lang != "Deutsch":
                    lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                    target_lang = lang_map.get(output_lang, "English")
                    final_result = translate_text_openai(final_result, "German", target_lang, api_key)
                st.subheader("Ergebnis des Compare-Mode:")
                st.write(final_result)
        else:
            st.write("### Einzel- oder Multi-Modus (kein Outlier-Check)")
            pdf_options = ["(Alle)"] + [f"{i+1}) {f.name}" for i, f in enumerate(uploaded_files)]
            selected_pdf = st.selectbox("Wähle eine PDF für Einzel-Analyse oder '(Alle)' für alle", pdf_options)
            if st.button("Analyse starten (Einzel-Modus)"):
                if selected_pdf == "(Alle)":
                    files_to_process = uploaded_files
                else:
                    idx = pdf_options.index(selected_pdf) - 1
                    files_to_process = [uploaded_files[idx]]
                final_result_text = []
                for fpdf in files_to_process:
                    text_data = ""
                    if action != "Tabellen & Grafiken":
                        with st.spinner(f"Extrahiere Text aus {fpdf.name}..."):
                            text_data = analyzer.extract_text_from_pdf(fpdf)
                            if not text_data.strip():
                                st.error(f"Kein Text aus {fpdf.name} extrahierbar.")
                                continue
                            st.success(f"Text aus {fpdf.name} extrahiert!")
                            st.session_state["paper_text"] = text_data[:15000]
                    result = ""
                    if action == "Zusammenfassung":
                        with st.spinner(f"Erstelle Zusammenfassung für {fpdf.name}..."):
                            result = analyzer.summarize(text_data, api_key)
                    elif action == "Wichtigste Erkenntnisse":
                        with st.spinner(f"Extrahiere Erkenntnisse aus {fpdf.name}..."):
                            result = analyzer.extract_key_findings(text_data, api_key)
                    elif action == "Methoden & Techniken":
                        with st.spinner(f"Identifiziere Methoden aus {fpdf.name}..."):
                            result = analyzer.identify_methods(text_data, api_key)
                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Bitte Thema angeben!")
                            return
                        with st.spinner(f"Bewerte Relevanz von {fpdf.name}..."):
                            result = analyzer.evaluate_relevance(text_data, topic, api_key)
                    elif action == "Tabellen & Grafiken":
                        with st.spinner(f"Suche Tabellen/Grafiken in {fpdf.name}..."):
                            all_tables_text = []
                            try:
                                with pdfplumber.open(fpdf) as pdf_:
                                    for page_number, page in enumerate(pdf_.pages, start=1):
                                        st.markdown(f"### Seite {page_number} in {fpdf.name}")
                                        tables = page.extract_tables()
                                        if tables:
                                            st.markdown("**Tabellen auf dieser Seite**")
                                            for table_idx, table_data in enumerate(tables, start=1):
                                                if not table_data:
                                                    st.write("Leere Tabelle erkannt.")
                                                    continue
                                                first_row = table_data[0]
                                                data_rows = table_data[1:]
                                                if not data_rows:
                                                    st.write("Nur Header vorhanden.")
                                                    data_rows = table_data
                                                    first_row = [f"Col_{i}" for i in range(len(data_rows[0]))]
                                                new_header = []
                                                used_cols = {}
                                                for col in first_row:
                                                    col_str = col if col else "N/A"
                                                    if col_str not in used_cols:
                                                        used_cols[col_str] = 1
                                                        new_header.append(col_str)
                                                    else:
                                                        used_cols[col_str] += 1
                                                        new_header.append(f"{col_str}.{used_cols[col_str]}")
                                                if any(len(row) != len(new_header) for row in data_rows):
                                                    st.write("Warnung: Inkonsistente Spaltenanzahl.")
                                                    df = pd.DataFrame(table_data)
                                                else:
                                                    df = pd.DataFrame(data_rows, columns=new_header)
                                                st.write(f"**Tabelle {table_idx}** in {fpdf.name}:")
                                                st.dataframe(df)
                                                table_str = df.to_csv(index=False)
                                                all_tables_text.append(f"Seite {page_number} - Tabelle {table_idx}\n{table_str}\n")
                                        else:
                                            st.write("Keine Tabellen hier.")
                                        images = page.images
                                        if images:
                                            st.markdown("**Bilder/Grafiken auf dieser Seite**")
                                            for img_index, img_dict in enumerate(images, start=1):
                                                xref = img_dict.get("xref")
                                                if xref is not None:
                                                    extracted_img = page.extract_image(xref)
                                                    if extracted_img:
                                                        image_data = extracted_img["image"]
                                                        image_obj = Image.open(io.BytesIO(image_data))
                                                        st.write(f"**Bild {img_index}** in {fpdf.name}:")
                                                        st.image(image_obj, use_column_width=True)
                                                    else:
                                                        st.write(f"Bild {img_index} konnte nicht extrahiert werden.")
                                        else:
                                            st.write("Keine Bilder hier.")
                                st.markdown(f"### Volltext-Suche 'Table' in {fpdf.name}")
                                try:
                                    text_all_pages = ""
                                    with pdfplumber.open(fpdf) as pdf2:
                                        for pg in pdf2.pages:
                                            t_ = pg.extract_text() or ""
                                            text_all_pages += t_ + "\n"
                                    lines = text_all_pages.splitlines()
                                    matches = [ln for ln in lines if "Table" in ln]
                                    if matches:
                                        st.write("Zeilen mit 'Table':")
                                        for ln in matches:
                                            st.write(f"- {ln}")
                                    else:
                                        st.write("Keine Erwähnung von 'Table'.")
                                except Exception as e2:
                                    st.warning(f"Fehler bei Volltext-Suche 'Table': {e2}")
                                if len(all_tables_text) > 0:
                                    combined_tables_text = "\n".join(all_tables_text)
                                    if len(combined_tables_text) > 14000:
                                        combined_tables_text = combined_tables_text[:14000] + "..."
                                    gpt_prompt = (
                                        "Bitte analysiere die folgenden Tabellen aus einem wissenschaftlichen PDF. "
                                        "Fasse die wichtigsten Erkenntnisse zusammen und gib (wenn möglich) eine kurze Interpretation in Bezug auf Lifestyle und Health Genetics:\n\n"
                                        f"{combined_tables_text}"
                                    )
                                    try:
                                        openai.api_key = api_key
                                        gpt_resp = openai.ChatCompletion.create(
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
                                        st.error(f"Fehler bei GPT-Tabellenanalyse: {str(e2)}")
                                        result = "(Fehler bei GPT-Auswertung)"
                                else:
                                    result = f"In {fpdf.name} keine Tabellen erkannt."
                            except Exception as e_:
                                st.error(f"Fehler in {fpdf.name}: {str(e_)}")
                                result = f"(Fehler in {fpdf.name})"
                    if action != "Tabellen & Grafiken" and result:
                        if output_lang != "Deutsch":
                            lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                            target_lang = lang_map.get(output_lang, "English")
                            result = translate_text_openai(result, "German", target_lang, api_key)
                    final_result_text.append(f"**Ergebnis für {fpdf.name}:**\n\n{result}")
                st.subheader("Ergebnis der (Multi-)Analyse (Einzelmodus):")
                st.markdown("\n\n---\n\n".join(final_result_text))
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_files:
            st.info("Bitte eine oder mehrere PDF-Dateien hochladen!")
    
    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe (Multi-PDF)")
    user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")
    
    # Hier: Für jedes Paper wird die Vorlage einzeln geladen, befüllt und als eigene Excel-Datei im ZIP abgelegt
    if uploaded_files and api_key:
        if st.button("Alle Analysen durchführen & in Excel speichern (Multi)"):
            with st.spinner("Analysiere alle hochgeladenen PDFs (für Excel)..."):
                # Bestimme die zu verarbeitenden Dateien (bei Compare-Mode ggf. nur relevante Paper)
                if compare_mode:
                    if not st.session_state["relevant_papers_compare"]:
                        paper_map_auto = {}
                        for fpdf in uploaded_files:
                            txt = analyzer.extract_text_from_pdf(fpdf)
                            if txt.strip():
                                paper_map_auto[fpdf.name] = txt
                        if not paper_map_auto:
                            st.error("Keine verwertbaren Paper.")
                            return
                        relevant_papers_auto, discovered_theme_auto = do_outlier_logic(paper_map_auto)
                        st.session_state["relevant_papers_compare"] = relevant_papers_auto
                        st.session_state["theme_compare"] = discovered_theme_auto
                    selected_files_for_excel = [f for f in uploaded_files if f.name in st.session_state["relevant_papers_compare"]]
                else:
                    selected_files_for_excel = uploaded_files
                
                output_zip_buffer = io.BytesIO()
                with zipfile.ZipFile(output_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for fpdf in selected_files_for_excel:
                        text = analyzer.extract_text_from_pdf(fpdf)
                        if not text.strip():
                            st.warning(f"Kein Text aus {fpdf.name} extrahierbar (evtl. kein OCR). Überspringe...")
                            continue
                        # Standardanalysen
                        summary_result = analyzer.summarize(text, api_key)
                        key_findings_result = analyzer.extract_key_findings(text, api_key)
                        relevance_result = (
                            analyzer.evaluate_relevance(text, topic, api_key)
                            if topic else "(No topic => keine Relevanz-Bewertung)"
                        )
                        methods_result = analyzer.identify_methods(text, api_key)
                        # Gene & rs-ID
                        pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                        match_text = re.search(pattern_obvious, text)
                        gene_via_text = match_text.group(1) if match_text else "n/a"
                        rs_pat = r"(rs\d+)"
                        found_rs_match = re.search(rs_pat, text)
                        rs_num = found_rs_match.group(1) if found_rs_match else "n/a"
                        # Genotypen extrahieren (bis zu 3)
                        genotype_regex = r"\b([ACGT]{2,3})\b"
                        found_genos = re.findall(genotype_regex, text)
                        unique_genos = []
                        for g in found_genos:
                            if g not in unique_genos:
                                unique_genos.append(g)
                            if len(unique_genos) >= 3:
                                break
                        # Populations-Frequenz
                        aff = AlleleFrequencyFinder()
                        freq_info = "Keine rsID" if rs_num=="n/a" else aff.build_freq_info_text(aff.get_allele_frequencies(rs_num) or {})
                        # Publikationsdatum (Dummy)
                        pub_date = "Not found"
                        # Studiengröße + Ethnicity
                        cohort_info = parse_cohort_info(summary_result)
                        study_size_ethnicity = (cohort_info["study_size"] + " " + cohort_info["origin"]).strip() or "n/a"
                        # Ergebnisse und Schlussfolgerungen
                        ergebnisse, schlussfolgerungen = split_summary(summary_result)
                        # Jetzt: Vorlage laden und befüllen
                        try:
                            wb_template = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                        except FileNotFoundError:
                            st.error("Die Datei 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                            return
                        ws = wb_template.active
                        # Zellen füllen
                        # D2: Compare-Thema
                        if compare_mode:
                            ws["D2"] = st.session_state["theme_compare"] if st.session_state["theme_compare"] else "N/A"
                        else:
                            ws["D2"] = user_defined_theme if theme_mode=="Manuell" else (st.session_state["theme_compare"] or "N/A")
                        ws["D5"] = gene_via_text
                        ws["D6"] = rs_num
                        # Genotypen und Frequenz in D10/E10, D11/E11, D12/E12
                        def fill_geno(row, geno):
                            ws[f"D{row}"] = geno
                            ws[f"E{row}"] = freq_info
                        if len(unique_genos) > 0:
                            fill_geno(10, unique_genos[0])
                        else:
                            ws["D10"], ws["E10"] = "n/a", "n/a"
                        if len(unique_genos) > 1:
                            fill_geno(11, unique_genos[1])
                        else:
                            ws["D11"], ws["E11"] = "n/a", "n/a"
                        if len(unique_genos) > 2:
                            fill_geno(12, unique_genos[2])
                        else:
                            ws["D12"], ws["E12"] = "n/a", "n/a"
                        ws["C20"] = pub_date
                        ws["D20"] = study_size_ethnicity
                        ws["E20"] = summary_result
                        ws["G21"] = ergebnisse
                        ws["G22"] = schlussfolgerungen
                        buf = io.BytesIO()
                        wb_template.save(buf)
                        buf.seek(0)
                        zf.writestr(f"analysis_results_{fpdf.name}.xlsx", buf.getvalue())
                output_zip_buffer.seek(0)
            st.success("Alle PDFs wurden in einzelne Excel-Dateien (basierend auf der Vorlage) geschrieben!")
            st.download_button(
                label="Download ZIP mit allen Excel-Dateien",
                data=output_zip_buffer,
                file_name="analysis_results_all.zip",
                mime="application/x-zip-compressed"
            )

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
    api_key = st.session_state.get("api_key", "")
    paper_text = st.session_state.get("paper_text", "")
    if not api_key:
        return f"(Kein API-Key) Echo: {question}"
    sys_msg = ("Du bist ein hilfreicher Assistent für allgemeine Fragen."
              if not paper_text.strip() else
              "Du bist ein hilfreicher Assistent, und hier ist ein Paper als Kontext:\n\n" +
              paper_text[:12000] + "\n\n" +
              "Bitte nutze es, um Fragen möglichst fachkundig zu beantworten.")
    openai.api_key = api_key
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": question}],
            temperature=0.3,
            max_tokens=400
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"OpenAI-Fehler: {e}"

def main():
    st.markdown(
        """
        <style>
        html, body { margin: 0; padding: 0; }
        .scrollable-chat {
            max-height: 400px; overflow-y: scroll; border: 1px solid #CCC;
            padding: 8px; margin-top: 10px; border-radius: 4px; background-color: #f9f9f9;
        }
        .message { padding: 0.5rem 1rem; border-radius: 15px; margin-bottom: 0.5rem; max-width: 80%; word-wrap: break-word; }
        .user-message { background-color: #e3f2fd; margin-left: auto; border-bottom-right-radius: 0; }
        .assistant-message { background-color: #f0f0f0; margin-right: auto; border-bottom-left-radius: 0; }
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
        st.markdown('<div class="scrollable-chat" id="chat-container">', unsafe_allow_html=True)
        for role, msg_text in st.session_state["chat_history"]:
            if role == "user":
                st.markdown(f'<div class="message user-message"><strong>Du:</strong> {msg_text}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="message assistant-message"><strong>Bot:</strong> {msg_text}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <script>
                function scrollToBottom() {
                    var container = document.getElementById('chat-container');
                    if(container) { container.scrollTop = container.scrollHeight; }
                }
                document.addEventListener('DOMContentLoaded', function() { scrollToBottom(); });
                const observer = new MutationObserver(function(mutations) { scrollToBottom(); });
                setTimeout(function() {
                    var container = document.getElementById('chat-container');
                    if(container) { observer.observe(container, { childList: true }); scrollToBottom(); }
                }, 1000);
            </script>
            """,
            unsafe_allow_html=True
        )

if __name__ == '__main__':
    main()
