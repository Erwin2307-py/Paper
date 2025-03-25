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

from typing import Dict, Any, Optional
from dotenv import load_dotenv
from PIL import Image
from scholarly import scholarly

from modules.online_api_filter import module_online_api_filter

# Neu: Excel / openpyxl-Import
import openpyxl

# Neuer Import für die Übersetzung mit google_trans_new
from google_trans_new import google_translator

# ------------------------------------------------------------------
# Hilfsfunktion: Setzt einen Zellwert, auch wenn die Zelle zusammengeführt (merged) ist.
# ------------------------------------------------------------------
def set_cell_value(ws, row, col, value):
    """
    Schreibt den Wert in die Zelle (row, col). Falls die Zelle Teil eines zusammengeführten Bereichs ist,
    wird der Wert in die oberste linke Zelle dieser Merge-Region geschrieben.
    """
    for merged_range in ws.merged_cells.ranges:
        if (row, col) in merged_range:
            ws.cell(row=merged_range.min_row, column=merged_range.min_col).value = value
            return
    ws.cell(row=row, column=col).value = value

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
    """Entfernt alle HTML-Tags außer <br>."""
    cleaned_text = re.sub(r'</?(?!br\b)[^>]*>', '', text)
    return cleaned_text

def translate_text_openai(text, source_language, target_language, api_key):
    """Übersetzt Text über OpenAI-ChatCompletion."""
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
        response = openai.ChatCompletion.create(
            model="gpt-4",
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
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 100, "resultType": "core"}
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
# Wichtige Klassen für die Analyse
# ------------------------------------------------------------------
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
        import openai
        openai.api_key = api_key
        if len(text) > 15000:
            text = text[:15000] + "..."
        prompt = prompt_template.format(text=text)
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Du bist ein Experte für die Analyse wissenschaftlicher Paper."},
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
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper. "
            "Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def identify_methods(self, text, api_key):
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden und Techniken. "
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
    """Klasse zum Abrufen und Anzeigen von Allelfrequenzen aus verschiedenen Quellen."""
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
        except requests.exceptions.HTTPError as e:
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

def split_summary(summary_text):
    pattern = re.compile(
        r'(Ergebnisse(?:\:|\s*\n)|Resultate(?:\:|\s*\n))(?P<results>.*?)(Schlussfolgerungen(?:\:|\s*\n)|Fazit(?:\:|\s*\n))(?P<conclusion>.*)',
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(summary_text)
    if match:
        ergebnisse = match.group('results').strip()
        schlussfolgerungen = match.group('conclusion').strip()
        return ergebnisse, schlussfolgerungen
    else:
        return summary_text, ""

def parse_cohort_info(summary_text: str) -> dict:
    info = {"study_size": "", "origin": ""}
    pattern_both = re.compile(
        r"(\d+)\s*Patient(?:en)?(?:[^\d]+)(\d+)\s*gesunde\s*Kontroll(?:personen)?",
        re.IGNORECASE
    )
    m_both = pattern_both.search(summary_text)
    if m_both:
        p_count = m_both.group(1)
        c_count = m_both.group(2)
        info["study_size"] = f"{p_count} Patienten / {c_count} Kontrollpersonen"
    else:
        pattern_single_p = re.compile(r"(\d+)\s*Patient(?:en)?", re.IGNORECASE)
        m_single_p = pattern_single_p.search(summary_text)
        if m_single_p:
            info["study_size"] = f"{m_single_p.group(1)} Patienten"
    pattern_origin = re.compile(r"in\s*der\s+(\S+)\s+Bevölkerung", re.IGNORECASE)
    m_orig = pattern_origin.search(summary_text)
    if m_orig:
        info["origin"] = m_orig.group(1).strip()
    return info

# ------------------------------------------------------------------
# NEUER Bereich: ChatGPT-Scoring (Codewörter + Gene)
# ------------------------------------------------------------------
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("Kein 'OPENAI_API_KEY' in st.secrets hinterlegt.")
        return []
    scored_results = []
    total = len(papers)
    progress = st.progress(0)
    status_text = st.empty()
    genes_str = ", ".join(genes) if genes else ""
    for idx, paper in enumerate(papers, start=1):
        current_title = paper.get("Title", "n/a")
        status_text.text(f"Verarbeite Paper {idx}/{total}: {current_title}")
        progress.progress(idx / total)
        title = paper.get("Title", "n/a")
        abstract = paper.get("Abstract", "n/a")
        prompt = f"""
Codewörter: {codewords}
Gene: {genes_str}

Paper:
Titel: {title}
Abstract: {abstract}

Gib mir eine Zahl von 0 bis 100 (Relevanz), wobei sowohl Codewörter als auch Gene berücksichtigt werden.
"""
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0
            )
            raw_text = resp.choices[0].message.content.strip()
            match = re.search(r'(\d+)', raw_text)
            if match:
                score = int(match.group(1))
            else:
                score = 0
        except Exception as e:
            st.error(f"ChatGPT Fehler beim Scoring: {e}")
            score = 0
        new_item = dict(paper)
        new_item["Relevance"] = score
        scored_results.append(new_item)
    status_text.empty()
    progress.empty()
    scored_results.sort(key=lambda x: x["Relevance"], reverse=True)
    return scored_results[:top_k]

# ------------------------------------------------------------------
# NEUER Bereich: Analyse von Gemeinsamkeiten & Widersprüchen
# ------------------------------------------------------------------
def analyze_papers_for_commonalities_and_contradictions(pdf_texts: Dict[str, str], api_key: str, model: str, method_choice: str = "Standard"):
    import openai
    openai.api_key = api_key
    all_claims = {}
    for fname, txt in pdf_texts.items():
        prompt_claims = f"""
Lies den folgenden Ausschnitt eines wissenschaftlichen Papers (maximal 2000 Tokens).
Extrahiere bitte die wichtigsten 3-5 "Aussagen" (Claims), die das Paper aufstellt.
Nutze als Ausgabe ein kompaktes JSON-Format, z.B:
[
  {{"claim": "Aussage 1"}},
  {{"claim": "Aussage 2"}}
]
Text: {txt[:6000]}
"""
        try:
            resp_claims = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt_claims}],
                temperature=0.3,
                max_tokens=700
            )
            raw = resp_claims.choices[0].message.content.strip()
            try:
                claims_list = json.loads(raw)
            except Exception:
                claims_list = [{"claim": raw}]
            if not isinstance(claims_list, list):
                claims_list = [claims_list]
            all_claims[fname] = claims_list
        except Exception as e:
            st.error(f"Fehler beim Claims-Extrahieren in {fname}: {e}")
            all_claims[fname] = []
    merged_claims = []
    for fname, cllist in all_claims.items():
        for cobj in cllist:
            ctext = cobj.get("claim", "(leer)")
            merged_claims.append({"paper": fname, "claim": ctext})
    big_input_str = json.dumps(merged_claims, ensure_ascii=False, indent=2)
    if method_choice == "ContraCrow":
        final_prompt = f"""
Nutze die ContraCrow-Methodik, um die folgenden Claims (Aussagen) aus mehreren wissenschaftlichen PDF-Papers zu analysieren. 
Die ContraCrow-Methodik fokussiert sich darauf, systematisch Gemeinsamkeiten und klare Widersprüche zu identifizieren.
Bitte identifiziere:
1) Die zentralen gemeinsamen Aussagen, die in den Papers auftreten.
2) Klare Widersprüche zwischen den Aussagen der verschiedenen Papers.
Antworte ausschließlich in folgendem JSON-Format (ohne zusätzliche Erklärungen):
{{
  "commonalities": [
    "Gemeinsamkeit 1",
    "Gemeinsamkeit 2"
  ],
  "contradictions": [
    {{"paperA": "...", "claimA": "...", "paperB": "...", "claimB": "...", "reason": "..." }},
    ...
  ]
}}
Hier die Claims:
{big_input_str}
"""
    else:
        final_prompt = f"""
Hier sind verschiedene Claims (Aussagen) aus mehreren wissenschaftlichen PDF-Papers im JSON-Format.
Bitte identifiziere:
1) Gemeinsamkeiten zwischen den Papers (Wo überschneiden oder ergänzen sich die Aussagen?)
2) Mögliche Widersprüche (Welche Aussagen widersprechen sich klar?)
Antworte NUR in folgendem JSON-Format (ohne zusätzliche Erklärungen):
{{
  "commonalities": [
    "Gemeinsamkeit 1",
    "Gemeinsamkeit 2"
  ],
  "contradictions": [
    {{"paperA": "...", "claimA": "...", "paperB": "...", "claimB": "...", "reason": "..." }},
    ...
  ]
}}
Hier die Claims:
{big_input_str}
"""
    try:
        resp_final = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": final_prompt}],
            temperature=0.0,
            max_tokens=1500
        )
        raw2 = resp_final.choices[0].message.content.strip()
        return raw2
    except Exception as e:
        return f"Fehler bei Gemeinsamkeiten/Widersprüche: {e}"

# ------------------------------------------------------------------
# Seite: Analyze Paper (inkl. PaperQA Multi-Paper Analyzer)
# ------------------------------------------------------------------
def page_analyze_paper():
    st.title("Analyze Paper - Integriert")
    
    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""
    
    st.sidebar.header("Einstellungen - PaperAnalyzer")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value
    
    model = st.sidebar.selectbox("OpenAI-Modell", ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4"], index=0)
    
    analysis_method = st.sidebar.selectbox("Analyse-Methode (Gemeinsamkeiten & Widersprüche)", ["Standard GPT", "ContraCrow"])
    compare_mode = st.sidebar.checkbox("Alle Paper gemeinsam vergleichen (Outlier ausschließen)?")
    theme_mode = st.sidebar.radio("Hauptthema bestimmen", ["Manuell", "GPT"])
    action = st.sidebar.radio(
        "Analyseart",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung", "Tabellen & Grafiken"],
        index=0
    )
    user_defined_theme = ""
    if theme_mode == "Manuell":
        user_defined_theme = st.sidebar.text_input("Manuelles Hauptthema (bei Compare-Mode)")
    
    topic = st.sidebar.text_input("Thema für Relevanz-Bewertung (falls relevant)")
    output_lang = st.sidebar.selectbox("Ausgabesprache", ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"], index=0)
    
    uploaded_files = st.file_uploader("PDF-Dateien hochladen", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]
    
    if "paper_texts" not in st.session_state:
        st.session_state["paper_texts"] = {}
    if "relevant_papers_compare" not in st.session_state:
        st.session_state["relevant_papers_compare"] = None
    if "theme_compare" not in st.session_state:
        st.session_state["theme_compare"] = ""
    
    # Dummy-Outlier-Logik (Platzhalter)
    def do_outlier_logic(paper_map: dict) -> (list, str):
        # Hier werden alle Paper als relevant betrachtet, Hauptthema wird als Dummy zurückgegeben.
        return list(paper_map.keys()), "Dummy-Hauptthema"
    
    # ------------------------- Einzel-/Multi-Modus (kein Outlier-Check) -------------------------
    if uploaded_files and api_key:
        st.write("### Einzel- oder Multi-Modus (kein Outlier-Check)")
        pdf_options = ["(Alle)"] + [f"{i+1}) {f.name}" for i, f in enumerate(uploaded_files)]
        selected_pdf = st.selectbox("Wähle eine PDF für Einzel-Analyse oder '(Alle)'", pdf_options)
        
        col_analysis, col_contradiction = st.columns(2)
        
        with col_analysis:
            if st.button("Analyse starten (Einzel-Modus)"):
                if selected_pdf == "(Alle)":
                    files_to_process = uploaded_files
                else:
                    idx = pdf_options.index(selected_pdf) - 1
                    if idx < 0:
                        st.warning("Keine Datei ausgewählt.")
                        return
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
                        result = "(Tabellen & Grafiken noch nicht implementiert)"
                    
                    if action != "Tabellen & Grafiken" and result:
                        if output_lang != "Deutsch":
                            lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                            target_lang = lang_map.get(output_lang, "English")
                            result = translate_text_openai(result, "German", target_lang, api_key)
                    final_result_text.append(f"**Ergebnis für {fpdf.name}:**\n\n{result}")
                
                st.subheader("Ergebnis der (Multi-)Analyse (Einzelmodus):")
                combined_output = "\n\n---\n\n".join(final_result_text)
                st.markdown(combined_output)
        
        with col_contradiction:
            st.write("Widerspruchsanalyse (Hochgeladene Paper)")
            if st.button("Widerspruchsanalyse jetzt starten"):
                if not st.session_state["paper_texts"]:
                    for upf in uploaded_files:
                        t_ = analyzer.extract_text_from_pdf(upf)
                        if t_.strip():
                            st.session_state["paper_texts"][upf.name] = t_
                paper_texts = st.session_state["paper_texts"]
                if not paper_texts:
                    st.error("Keine Texte für die Widerspruchsanalyse vorhanden (hochgeladene Paper).")
                else:
                    with st.spinner("Analysiere hochgeladene Paper auf Gemeinsamkeiten & Widersprüche..."):
                        result_json_str = analyze_papers_for_commonalities_and_contradictions(
                            pdf_texts=paper_texts,
                            api_key=api_key,
                            model=model,
                            method_choice="ContraCrow" if analysis_method == "ContraCrow" else "Standard"
                        )
                        st.subheader("Ergebnis der Widerspruchsanalyse (Hochgeladene Paper) (JSON)")
                        st.code(result_json_str, language="json")
                        try:
                            data_js = json.loads(result_json_str)
                            common = data_js.get("commonalities", [])
                            contras = data_js.get("contradictions", [])
                            st.write("## Gemeinsamkeiten")
                            if common:
                                for c in common:
                                    st.write(f"- {c}")
                            else:
                                st.info("Keine Gemeinsamkeiten erkannt.")
                            st.write("## Widersprüche")
                            if contras:
                                for i, cobj in enumerate(contras, start=1):
                                    st.write(f"Widerspruch {i}:")
                                    st.write(f"- **Paper A**: {cobj.get('paperA')} => {cobj.get('claimA')}")
                                    st.write(f"- **Paper B**: {cobj.get('paperB')} => {cobj.get('claimB')}")
                                    st.write(f"  Grund: {cobj.get('reason','(none)')}")
                            else:
                                st.info("Keine Widersprüche erkannt.")
                        except Exception as e:
                            st.warning(f"Die GPT-Ausgabe konnte nicht als valides JSON geparst werden.\nFehler: {e}")
    
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_files:
            st.info("Bitte eine oder mehrere PDF-Dateien hochladen!")
    
    # ------------------------- Excel-Ausgabe (Multi-PDF) -------------------------
    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe (Multi-PDF)")
    user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")
    
    if uploaded_files and api_key:
        if st.button("Alle Analysen durchführen & in Excel speichern (Multi)"):
            with st.spinner("Analysiere alle hochgeladenen PDFs (für Excel)..."):
                analyzer = PaperAnalyzer(model=model)
                
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
                    selected_files_for_excel = [f for f in uploaded_files if f.name in st.session_state.get("relevant_papers_compare", [])]
                else:
                    selected_files_for_excel = uploaded_files
                
                for fpdf in selected_files_for_excel:
                    text = analyzer.extract_text_from_pdf(fpdf)
                    if not text.strip():
                        st.error(f"Kein Text aus {fpdf.name} extrahierbar (evtl. kein OCR). Überspringe...")
                        continue
                    
                    summary_de = analyzer.summarize(text, api_key)
                    key_findings_result = analyzer.extract_key_findings(text, api_key)
                    if not topic:
                        relevance_result = "(No topic => no Relevanz-Bewertung)"
                    else:
                        relevance_result = analyzer.evaluate_relevance(text, topic, api_key)
                    methods_result = analyzer.identify_methods(text, api_key)
                    
                    # Gene und Rs-ID extrahieren
                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    match_text = re.search(pattern_obvious, text)
                    gene_via_text = match_text.group(1) if match_text else ""
                    found_gene = gene_via_text  # Genname in D5
                    rs_pat = re.compile(r"(rs\d+)", re.IGNORECASE)
                    found_rs_match = re.search(rs_pat, text)
                    rs_num = found_rs_match.group(1) if found_rs_match else "n/a"  # Rs-Nummer in D6
                    
                    # Genotypen ermitteln
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
                    
                    # Populationsfrequenz ermitteln
                    aff = AlleleFrequencyFinder()
                    freq_info = "Keine rsID vorhanden"
                    if rs_num.lower() != "n/a":
                        data = aff.get_allele_frequencies(rs_num)
                        if not data:
                            data = aff.try_alternative_source(rs_num)
                        if data:
                            freq_info = aff.build_freq_info_text(data)
                    
                    # Zusammenfassung splitten
                    results_text, conclusion_text = split_summary(summary_de)
                    cohort_data = parse_cohort_info(summary_de)
                    study_size = cohort_data.get("study_size", "N/A")
                    
                    try:
                        wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                    except FileNotFoundError:
                        st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                        return
                    ws = wb.active
                    
                    # Excel-Zuordnung gemäß neuer Vorgaben:
                    # D2: Hauptthema (aus st.session_state["theme_compare"])
                    set_cell_value(ws, 2, 4, st.session_state.get("theme_compare", "N/A"))
                    
                    # D5: Genname, E5: LEER (nichts schreiben)
                    set_cell_value(ws, 5, 4, found_gene)
                    set_cell_value(ws, 5, 5, "")  # Leerlassen
                    
                    # D6: Rs-Nummer
                    set_cell_value(ws, 6, 4, rs_num)
                    
                    # D10: Erster Genotyp, E10: Populationsfrequenz
                    # D11: Zweiter Genotyp, E11: Populationsfrequenz
                    # D12: Dritter Genotyp, E12: Populationsfrequenz
                    for i in range(3):
                        row_index = 10 + i
                        if i < len(unique_geno_pairs):
                            set_cell_value(ws, row_index, 4, unique_geno_pairs[i][0])
                        else:
                            set_cell_value(ws, row_index, 4, "")
                        set_cell_value(ws, row_index, 5, freq_info)
                    
                    # C20: Datum der Publikation ("N/A")
                    set_cell_value(ws, 20, 3, "N/A")
                    # D20: Study Size
                    set_cell_value(ws, 20, 4, study_size)
                    # E20: Key Findings
                    set_cell_value(ws, 20, 5, key_findings_result)
                    # G21: Results
                    set_cell_value(ws, 21, 7, results_text)
                    # G22: Conclusion
                    set_cell_value(ws, 22, 7, conclusion_text)
                    
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # Optional: Falls Datum des Excel-Exports gewünscht in J2:
                    set_cell_value(ws, 2, 10, now_str)
                    
                    output_buffer = io.BytesIO()
                    wb.save(output_buffer)
                    output_buffer.seek(0)
                    
                    xlsx_name = f"analysis_{fpdf.name.replace('.pdf','')}.xlsx"
                    st.download_button(
                        label=f"Download Excel für {fpdf.name}",
                        data=output_buffer,
                        file_name=xlsx_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_files:
            st.info("Bitte eine oder mehrere PDF-Dateien hochladen!")
    
    st.write("---")
    st.write("## Einzelanalyse der nach ChatGPT-Scoring ausgewählten Paper")
    if "scored_list" not in st.session_state or not st.session_state["scored_list"]:
        if "search_results" in st.session_state and st.session_state["search_results"]:
            st.info("Es wurden noch keine gescorten Paper gespeichert. Scoring wird jetzt durchgeführt...")
            codewords_str = st.session_state.get("codewords", "")
            selected_genes = st.session_state.get("selected_genes", [])
            scored_list = chatgpt_online_search_with_genes(
                papers=st.session_state["search_results"],
                codewords=codewords_str,
                genes=selected_genes,
                top_k=200
            )
            st.session_state["scored_list"] = scored_list
            st.success("Scored Paper erfolgreich in st.session_state['scored_list'] gespeichert!")
        else:
            st.info("Keine gescorten Paper vorhanden (st.session_state['scored_list']).")
            return
    st.subheader("Einzelanalyse der nach ChatGPT-Scoring ausgewählten Paper")
    scored_titles = [paper["Title"] for paper in st.session_state.get("scored_list", [])]
    chosen_title = st.selectbox("Wähle ein Paper aus der Scoring-Liste:", options=["(Bitte wählen)"] + scored_titles)
    if chosen_title != "(Bitte wählen)":
        selected_paper = next((p for p in st.session_state["scored_list"] if p["Title"] == chosen_title), None)
        if selected_paper:
            st.write("**Titel:** ", selected_paper.get("Title", "n/a"))
            st.write("**Quelle:** ", selected_paper.get("Source", "n/a"))
            st.write("**PubMed ID:** ", selected_paper.get("PubMed ID", "n/a"))
            st.write("**Jahr:** ", selected_paper.get("Year", "n/a"))
            st.write("**Publisher:** ", selected_paper.get("Publisher", "n/a"))
            st.write("**Abstract:**")
            abstract = selected_paper.get("Abstract") or ""
            if abstract.strip():
                st.markdown(f"> {abstract}")
            else:
                st.warning(f"Kein Abstract für {selected_paper.get('Title', 'Unbenannt')} vorhanden.")
        else:
            st.warning("Paper nicht gefunden (unerwarteter Fehler).")
    
    st.write("---")
    st.header("PaperQA Multi-Paper Analyzer: Gemeinsamkeiten & Widersprüche (Gescorte Paper)")
    if st.button("Analyse (Gescorte Paper) durchführen"):
        if "scored_list" in st.session_state and st.session_state["scored_list"]:
            paper_texts = {}
            for paper in st.session_state["scored_list"]:
                title = paper.get("Title", "Unbenannt")
                abstract = paper.get("Abstract") or ""
                if abstract.strip():
                    paper_texts[title] = abstract
                else:
                    st.warning(f"Kein Abstract für {title} vorhanden.")
            if not paper_texts:
                st.error("Keine Texte für die Analyse vorhanden.")
            else:
                with st.spinner("Analysiere gescorte Paper auf Gemeinsamkeiten & Widersprüche..."):
                    result_json_str = analyze_papers_for_commonalities_and_contradictions(
                        paper_texts,
                        api_key,
                        model,
                        method_choice="ContraCrow" if analysis_method == "ContraCrow" else "Standard"
                    )
                    st.subheader("Ergebnis (JSON)")
                    st.code(result_json_str, language="json")
                    try:
                        data_js = json.loads(result_json_str)
                        common = data_js.get("commonalities", [])
                        contras = data_js.get("contradictions", [])
                        st.write("## Gemeinsamkeiten")
                        if common:
                            for c in common:
                                st.write(f"- {c}")
                        else:
                            st.info("Keine Gemeinsamkeiten erkannt.")
                        st.write("## Widersprüche")
                        if contras:
                            for i, cobj in enumerate(contras, start=1):
                                st.write(f"Widerspruch {i}:")
                                st.write(f"- **Paper A**: {cobj.get('paperA')} => {cobj.get('claimA')}")
                                st.write(f"- **Paper B**: {cobj.get('paperB')} => {cobj.get('claimB')}")
                                st.write(f"  Grund: {cobj.get('reason','(none)')}")
                        else:
                            st.info("Keine Widersprüche erkannt.")
                    except Exception as e:
                        st.warning(f"Die GPT-Ausgabe konnte nicht als valides JSON geparst werden.\nFehler: {e}")
        else:
            st.error("Keine gescorten Paper vorhanden. Bitte zuerst Scoring durchführen.")

# ------------------------------------------------------------------
# Sidebar Navigation und Chatbot
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
        response = openai.ChatCompletion.create(
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

def main():
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        .scrollable-chat {
            max-height: 400px; 
            overflow-y: scroll; 
            border: 1px solid #CCC;
            padding: 8px;
            margin-top: 10px;
            border-radius: 4px;
            background-color: #f9f9f9;
        }
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
                    if(container) {
                        container.scrollTop = container.scrollHeight;
                    }
                }
                document.addEventListener('DOMContentLoaded', function() {
                    scrollToBottom();
                });
                const observer = new MutationObserver(function(mutations) {
                    scrollToBottom();
                });
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

if __name__ == '__main__':
    main()
