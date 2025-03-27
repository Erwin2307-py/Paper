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

# Neu: Excel / openpyxl-Import
import openpyxl

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
# 1) Allgemeine Hilfsfunktionen
# ------------------------------------------------------------------
def clean_html_except_br(text: str) -> str:
    """Removes all HTML tags except <br>."""
    return re.sub(r'</?(?!br\b)[^>]*>', '', text)

def translate_text_openai(text: str, source_language: str, target_language: str, api_key: str) -> str:
    """Uses OpenAI ChatCompletion to translate text from one language to another."""
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
        return clean_html_except_br(translation)
    except Exception as e:
        st.warning(f"Translation error: {e}")
        return text

# ------------------------------------------------------------------
# CORE API
# ------------------------------------------------------------------
class CoreAPI:
    def __init__(self, api_key: str):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query: str, filters=None, sort=None, limit=100) -> Dict[str, Any]:
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

def check_core_aggregate_connection(api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF", timeout=15) -> bool:
    """Checks if the CORE aggregator is reachable."""
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query: str, api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF") -> list:
    """Simple search on the CORE aggregator."""
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
# 2) PubMed
# ------------------------------------------------------------------
def check_pubmed_connection(timeout=10) -> bool:
    """Quick check to see if PubMed is reachable."""
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def search_pubmed_simple(query: str) -> list:
    """Simple search (title/journal/year) on PubMed."""
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

def fetch_pubmed_abstract(pmid: str) -> str:
    """Fetches the abstract for a given PubMed ID via EFetch."""
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

def fetch_pubmed_doi_and_link(pmid: str) -> (str, str):
    """
    Attempts to retrieve the DOI and a link to the paper via PubMed.
    Returns (doi, pubmed_link).
    If no DOI is found, returns ("n/a", link).
    """
    if not pmid or pmid == "n/a":
        return ("n/a", "")

    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        rs = requests.get(summary_url, params=params_sum, timeout=8)
        rs.raise_for_status()
        data = rs.json()
        result_obj = data.get("result", {}).get(pmid, {})
        eloc = result_obj.get("elocationid", "")
        if eloc and eloc.startswith("doi:"):
            doi_ = eloc.split("doi:", 1)[1].strip()
            if doi_:
                return (doi_, link)
    except Exception:
        pass

    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params_efetch = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r_ef = requests.get(efetch_url, params=params_efetch, timeout=8)
        r_ef.raise_for_status()
        root = ET.fromstring(r_ef.content)
        doi_found = "n/a"
        for aid in root.findall(".//ArticleId"):
            id_type = aid.attrib.get("IdType", "")
            if id_type.lower() == "doi":
                if aid.text:
                    doi_found = aid.text.strip()
                    break
        return (doi_found, link)
    except Exception:
        return ("n/a", link)

# ------------------------------------------------------------------
# 3) Europe PMC
# ------------------------------------------------------------------
def check_europe_pmc_connection(timeout=10) -> bool:
    """Checks connectivity to Europe PMC."""
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

def search_europe_pmc_simple(query: str) -> list:
    """Simple search in Europe PMC."""
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

def fetch_openalex_data(entity_type: str, entity_id: Optional[str] = None, params: Optional[dict] = None) -> Optional[dict]:
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
        st.error(f"Error: {response.status_code} - {response.text}")
        return None

def search_openalex_simple(query: str) -> Optional[dict]:
    """Simple version: just fetches raw data and checks if something comes back."""
    search_params = {"search": query}
    return fetch_openalex_data("works", params=search_params)

# ------------------------------------------------------------------
# 5) Google Scholar
# ------------------------------------------------------------------
class GoogleScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_google_scholar(self, base_query: str):
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
            st.error(f"Google Scholar Search Error: {e}")

# ------------------------------------------------------------------
# 6) Semantic Scholar
# ------------------------------------------------------------------
def check_semantic_scholar_connection(timeout=10) -> bool:
    """Checks connectivity to Semantic Scholar."""
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

    def search_semantic_scholar(self, base_query: str):
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
# Seite: PaperAnalyzer und Hilfsfunktionen
# ------------------------------------------------------------------
class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def extract_text_from_pdf(self, pdf_file) -> str:
        """Extracts raw text from a PDF via PyPDF2."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text: str, prompt_template: str, api_key: str) -> str:
        """Helper function to call OpenAI ChatCompletion."""
        import openai
        openai.api_key = api_key
        if len(text) > 15000:
            text = text[:15000] + "..."
        prompt = prompt_template.format(text=text)
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert in analyzing scientific papers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def summarize(self, text: str, api_key: str) -> str:
        """
        Creates a structured summary in German, then we can translate if needed.
        """
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden wissenschaftlichen Papers. "
            "Gliedere sie in mindestens vier klar getrennte Abschnitte (z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text: str, api_key: str) -> str:
        """Extract 5 key findings (German)."""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper. "
            "Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text: str, api_key: str) -> str:
        """Identifies methods and techniques (German)."""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden und Techniken. "
            "Gib zu jeder Methode eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text: str, topic: str, api_key: str) -> str:
        """Rates the relevance to a topic (scale 1-10, in German)."""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf einer Skala von 1-10. "
            f"Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

class AlleleFrequencyFinder:
    """
    Class that fetches allele frequencies from Ensembl and calculates genotype frequencies
    via Hardy-Weinberg for a user-defined genotype (AA, AG, GG, etc.).
    """
    def __init__(self):
        self.ensembl_server = "https://rest.ensembl.org"
        self.max_retries = 3
        self.retry_delay = 2

    def get_variant_info(self, rs_id: str) -> Optional[Dict[str, Any]]:
        """Fetch variant info from Ensembl (including population data)."""
        if not rs_id.startswith("rs"):
            rs_id = "rs" + rs_id
        ext = f"/variation/human/{rs_id}?pops=1"
        try:
            r = requests.get(self.ensembl_server + ext, headers={"Content-Type": "application/json"}, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def calculate_genotype_frequency(self, data: Dict[str, Any], genotype: str) -> Dict[str, float]:
        """
        Computes genotype frequency based on allele frequencies (Hardy-Weinberg).

        Returns dict of { population_name: genotype_frequency } for 1000GENOMES populations.
        """
        if not data or 'populations' not in data:
            return {}
        genotype = genotype.upper()
        if len(genotype) != 2:
            return {}

        allele1, allele2 = genotype[0], genotype[1]
        results = {}
        pops = data['populations']

        # For each population (only 1000GENOMES)
        # gather allele frequencies, then compute Hardy-Weinberg
        for population in pops:
            pop_name = population.get('population', '')
            if '1000GENOMES' not in pop_name:
                continue
            # collect all allele frequencies for this pop_name
            allele_freqs = {}
            for p2 in pops:
                if p2.get('population') == pop_name:
                    a_ = p2.get('allele', '')
                    freq_ = p2.get('frequency', 0.0)
                    allele_freqs[a_] = freq_

            if allele1 not in allele_freqs or allele2 not in allele_freqs:
                continue

            # HW
            if allele1 == allele2:
                freq_ = allele_freqs[allele1] ** 2
            else:
                freq_ = 2 * allele_freqs[allele1] * allele_freqs[allele2]
            results[pop_name] = freq_

        return results

    def build_freq_info_text(self, rs_id: str, genotype: str) -> str:
        """
        Builds an English text about genotype frequency for the global population.
        Example: 'Global population frequency (rs699, AA): 0.0274'
        If no data => 'No frequency data'.
        """
        data = self.get_variant_info(rs_id)
        if not data:
            return f"No frequency data for {rs_id}"

        genotype_freqs = self.calculate_genotype_frequency(data, genotype)
        if not genotype_freqs:
            return f"No genotype frequency found for {rs_id} ({genotype})"

        # Show the global pop freq first if it exists:
        global_key = "1000GENOMES:phase_3:ALL"
        if global_key in genotype_freqs:
            gf = genotype_freqs[global_key]
            return f"Global population frequency ({rs_id}, {genotype}): {gf:.4f}"
        else:
            return f"No global population frequency for {rs_id} ({genotype})"

# ------------------------------------------------------------------
# Helper for splitting and parsing cohorts
# ------------------------------------------------------------------
def split_summary(summary_text: str) -> (str, str):
    """
    Attempts to separate 'Ergebnisse/Resultate' from 'Schlussfolgerungen/Fazit' in German.
    """
    pattern = re.compile(
        r'(Ergebnisse(?:\:|\s*\n)|Resultate(?:\:|\s*\n))(?P<results>.*?)(Schlussfolgerungen(?:\:|\s*\n)|Fazit(?:\:|\s*\n))(?P<conclusion>.*)',
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(summary_text)
    if match:
        ergebnisse = match.group('results').strip()
        schlussfolgerungen = match.group('conclusion').strip()
        return ergebnisse, schlussfolgerungen
    return summary_text, ""

def parse_cohort_info(summary_text: str) -> dict:
    """
    Attempts to parse info about the cohort in a German summary (like #patients, origin).
    """
    info = {"study_size": "", "origin": ""}
    pattern_both = re.compile(
        r"(\d+)\s*Patient(?:en)?(?:[^\d]+)(\d+)\s*gesunde\s*Kontroll(?:personen)?",
        re.IGNORECASE
    )
    m_both = pattern_both.search(summary_text)
    if m_both:
        p_count = m_both.group(1)
        c_count = m_both.group(2)
        info["study_size"] = f"{p_count} patients / {c_count} healthy controls"
    else:
        pattern_single_p = re.compile(r"(\d+)\s*Patient(?:en)?", re.IGNORECASE)
        m_single_p = pattern_single_p.search(summary_text)
        if m_single_p:
            info["study_size"] = f"{m_single_p.group(1)} patients"

    pattern_origin = re.compile(r"in\s*der\s+(\S+)\s+Bevölkerung", re.IGNORECASE)
    m_orig = pattern_origin.search(summary_text)
    if m_orig:
        info["origin"] = m_orig.group(1).strip()
    return info

def fetch_pubmed_doi_and_link(pmid: str) -> (str, str):
    """
    Attempt to retrieve the DOI and pubmed link from PubMed.
    Returns (doi, link).
    """
    if not pmid or pmid == "n/a":
        return ("n/a", "")
    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        rs = requests.get(summary_url, params=params_sum, timeout=8)
        rs.raise_for_status()
        data = rs.json()
        result_obj = data.get("result", {}).get(pmid, {})
        eloc = result_obj.get("elocationid", "")
        if eloc and eloc.startswith("doi:"):
            doi_ = eloc.split("doi:", 1)[1].strip()
            if doi_:
                return (doi_, link)
    except Exception:
        pass

    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params_efetch = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r_ef = requests.get(efetch_url, params=params_efetch, timeout=8)
        r_ef.raise_for_status()
        root = ET.fromstring(r_ef.content)
        doi_found = "n/a"
        for aid in root.findall(".//ArticleId"):
            id_type = aid.attrib.get("IdType", "")
            if id_type.lower() == "doi":
                if aid.text:
                    doi_found = aid.text.strip()
                    break
        return (doi_found, link)
    except Exception:
        return ("n/a", link)

# ------------------------------------------------------------------
# ChatGPT-based scoring (unchanged)
# ------------------------------------------------------------------
def chatgpt_online_search_with_genes(papers: list, codewords: str, genes: list, top_k=100) -> list:
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("No 'OPENAI_API_KEY' in st.secrets.")
        return []
    scored_results = []
    total = len(papers)
    progress = st.progress(0)
    status_text = st.empty()
    genes_str = ", ".join(genes) if genes else ""
    for idx, paper in enumerate(papers, start=1):
        current_title = paper.get("Title", "n/a")
        status_text.text(f"Scoring paper {idx}/{total}: {current_title}")
        progress.progress(idx / total)
        title = paper.get("Title", "n/a")
        abstract = paper.get("Abstract", "n/a")
        prompt = f"""
Codewords: {codewords}
Genes: {genes_str}

Paper:
Title: {title}
Abstract: {abstract}

Please give me a score from 0 to 100 (relevance), taking into account codewords and genes.
"""
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0
            )
            raw_text = resp.choices[0].message.content.strip()
            match_ = re.search(r'(\d+)', raw_text)
            if match_:
                score = int(match_.group(1))
            else:
                score = 0
        except Exception as e:
            st.error(f"ChatGPT scoring error: {e}")
            score = 0
        new_item = dict(paper)
        new_item["Relevance"] = score
        scored_results.append(new_item)
    status_text.empty()
    progress.empty()
    scored_results.sort(key=lambda x: x["Relevance"], reverse=True)
    return scored_results[:top_k]

# ------------------------------------------------------------------
# Commonalities and contradictions
# ------------------------------------------------------------------
def analyze_papers_for_commonalities_and_contradictions(
    pdf_texts: Dict[str, str],
    api_key: str,
    model: str,
    method_choice: str = "Standard"
) -> str:
    import openai
    openai.api_key = api_key

    # 1) Extract claims per paper
    all_claims = {}
    for fname, txt in pdf_texts.items():
        prompt_claims = f"""
Please read the following text of a scientific paper (max 2000 tokens).
Extract the 3-5 key claims the paper makes.
Use a compact JSON format, e.g:
[
  {{"claim": "Claim 1"}},
  {{"claim": "Claim 2"}}
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
            st.error(f"Error extracting claims in {fname}: {e}")
            all_claims[fname] = []

    merged_claims = []
    for fname, cllist in all_claims.items():
        for cobj in cllist:
            ctext = cobj.get("claim", "(none)")
            merged_claims.append({
                "paper": fname,
                "claim": ctext
            })
    big_input_str = json.dumps(merged_claims, ensure_ascii=False, indent=2)

    # 2) Identify commonalities + contradictions
    if method_choice == "ContraCrow":
        final_prompt = f"""
Use the ContraCrow methodology to analyze the following claims from multiple scientific PDF papers.
Identify:
1) The central common statements across the papers.
2) Clear contradictions between statements of different papers.

Answer in JSON only (no additional explanations):
{{
  "commonalities": [
    "Commonality 1",
    "Commonality 2"
  ],
  "contradictions": [
    {{"paperA": "...", "claimA": "...", "paperB": "...", "claimB": "...", "reason": "..."}},
    ...
  ]
}}

Here are the claims:
{big_input_str}
"""
    else:
        final_prompt = f"""
We have multiple claims (statements) from several scientific PDF papers in JSON format.
Please identify:
1) Commonalities between the papers.
2) Potential contradictions (which statements clearly conflict?).

Answer in JSON only (no further explanations):
{{
  "commonalities": [
    "Commonality 1",
    "Commonality 2"
  ],
  "contradictions": [
    {{"paperA": "...", "claimA": "...", "paperB": "...", "claimB": "...", "reason": "..."}},
    ...
  ]
}}

Here are the claims:
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
        return f"Error with commonalities/contradictions: {e}"

# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------
def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Please choose a module on the left sidebar to proceed.")

def page_online_api_filter():
    st.title("Online-API Filter")
    st.write("This page can combine API selection and filtering in one step. Implementation as needed.")

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    st.write("Implementation for codeword-based searching in PubMed would go here.")

def page_analyze_paper():
    st.title("Analyze Paper")
    """
    This function manages uploading PDFs, analyzing them with ChatGPT, computing genotype frequencies,
    and storing all results in an English-based Excel file.
    """
    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""

    st.sidebar.header("PaperAnalyzer Settings")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value

    model = st.sidebar.selectbox("OpenAI Model", ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4"], index=0)
    analysis_method = st.sidebar.selectbox("Method (Commonalities & Contradictions)", ["Standard GPT", "ContraCrow"])
    compare_mode = st.sidebar.checkbox("Compare all papers (exclude outliers)?")
    theme_mode = st.sidebar.radio("Determine main theme", ["Manuell", "GPT"])
    action = st.sidebar.radio(
        "Analysis type",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung", "Tabellen & Grafiken"],
        index=0
    )
    user_defined_theme = ""
    if theme_mode == "Manuell":
        user_defined_theme = st.sidebar.text_input("Manual main theme (for compare mode)")

    topic = st.sidebar.text_input("Topic for relevance scoring (optional)")
    output_lang = st.sidebar.selectbox("Output Language (UI only)", ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"], index=0)

    uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]

    if "paper_texts" not in st.session_state:
        st.session_state["paper_texts"] = {}
    if "relevant_papers_compare" not in st.session_state:
        st.session_state["relevant_papers_compare"] = None
    if "theme_compare" not in st.session_state:
        st.session_state["theme_compare"] = ""

    def do_outlier_logic(paper_map: dict) -> (list, str):
        """
        Uses GPT to decide which papers match the theme, and possibly identify the main theme.
        """
        if theme_mode == "Manuell":
            main_theme = user_defined_theme.strip()
            if not main_theme:
                st.error("Please provide a manual main theme.")
                return ([], "")
            snippet_list = []
            for name, txt_data in paper_map.items():
                snippet = txt_data[:700].replace("\n", " ")
                snippet_list.append(f'{{"filename":"{name}","snippet":"{snippet}"}}')
            big_snippet = ",\n".join(snippet_list)
            big_input = f"""
The user has defined the main theme: '{main_theme}'.

These are multiple papers in JSON form. Decide per paper if it is relevant to the theme or not.
At the end, output JSON in the format:
{{
  "theme":"repeat the user-defined theme",
  "papers":[
    {{"filename":"...","relevant":true/false,"reason":"short reason"}}
  ]
}}

Only the JSON, no extra text.

[{big_snippet}]
"""
            import openai
            openai.api_key = api_key
            try:
                scope_resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You check paper snippets for relevance to a user theme."},
                        {"role": "user", "content": big_input}
                    ],
                    temperature=0.0,
                    max_tokens=1800
                )
                scope_decision = scope_resp.choices[0].message.content
            except Exception as e1:
                st.error(f"GPT error in compare-mode (manual): {e1}")
                return ([], "")
            st.markdown("#### GPT Output (Outlier Check / Manual):")
            st.code(scope_decision, language="json")
            json_str = scope_decision.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"```[\w]*\n?", "", json_str)
                json_str = re.sub(r"\n?```", "", json_str)
            try:
                data_parsed = json.loads(json_str)
                papers_info = data_parsed.get("papers", [])
            except Exception as parse_e:
                st.error(f"JSON parse error: {parse_e}")
                return ([], "")
            st.write(f"**Main Theme (Manual)**: {main_theme}")
            relevant_papers_local = []
            st.write("**Paper Classification**:")
            for p in papers_info:
                fname = p.get("filename", "?")
                rel = p.get("relevant", False)
                reason = p.get("reason", "")
                if rel:
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Reason: {reason}")
                else:
                    st.warning(f"{fname} => NOT relevant. Reason: {reason}")
            return (relevant_papers_local, main_theme)
        else:
            # GPT tries to find a main theme and decide relevance
            snippet_list = []
            for name, txt_data in paper_map.items():
                snippet = txt_data[:700].replace("\n", " ")
                snippet_list.append(f'{{"filename":"{name}","snippet":"{snippet}"}}')
            big_snippet = ",\n".join(snippet_list)
            big_input = f"""
Here are multiple papers in JSON form. Please figure out the common main theme, 
then respond with JSON:
{{
  "main_theme":"short theme desc",
  "papers":[
    {{"filename":"...","relevant":true/false,"reason":"short reason"}}
  ]
}}

Only that JSON. No further explanation.

[{big_snippet}]
"""
            import openai
            openai.api_key = api_key
            try:
                scope_resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an assistant that filters papers by theme."},
                        {"role": "user", "content": big_input}
                    ],
                    temperature=0.0,
                    max_tokens=1800
                )
                scope_decision = scope_resp.choices[0].message.content
            except Exception as e1:
                st.error(f"GPT error in compare-mode: {e1}")
                return ([], "")
            st.markdown("#### GPT Output (Outlier Check / GPT):")
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
                st.error(f"JSON parse error: {parse_e}")
                return ([], "")
            st.write(f"**Main Theme (GPT)**: {main_theme}")
            relevant_papers_local = []
            st.write("**Paper Classification**:")
            for p in papers_info:
                fname = p.get("filename", "?")
                rel = p.get("relevant", False)
                reason = p.get("reason", "")
                if rel:
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Reason: {reason}")
                else:
                    st.warning(f"{fname} => NOT relevant. Reason: {reason}")
            return (relevant_papers_local, main_theme)

    if uploaded_files and api_key:
        # Compare Mode
        if compare_mode:
            st.write("### Compare Mode: Exclude outlier papers")
            if st.button("Start Compare-Analysis"):
                paper_map = {}
                for fpdf in uploaded_files:
                    txt = analyzer.extract_text_from_pdf(fpdf)
                    if txt.strip():
                        paper_map[fpdf.name] = txt
                    else:
                        st.warning(f"No text extracted from {fpdf.name}, skipping.")
                if not paper_map:
                    st.error("No usable papers.")
                    return
                relevant_papers, discovered_theme = do_outlier_logic(paper_map)
                st.session_state["relevant_papers_compare"] = relevant_papers
                st.session_state["theme_compare"] = discovered_theme
                if not relevant_papers:
                    st.error("No relevant papers after outlier-check.")
                    return
                combined_text = ""
                for rp in relevant_papers:
                    combined_text += f"\n=== {rp} ===\n{paper_map[rp]}"
                if action == "Tabellen & Grafiken":
                    final_result = "Table & Figure analysis not implemented in compare-mode."
                else:
                    if action == "Zusammenfassung":
                        final_result = analyzer.summarize(combined_text, api_key)
                    elif action == "Wichtigste Erkenntnisse":
                        final_result = analyzer.extract_key_findings(combined_text, api_key)
                    elif action == "Methoden & Techniken":
                        final_result = analyzer.identify_methods(combined_text, api_key)
                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Please specify a topic!")
                            return
                        final_result = analyzer.evaluate_relevance(combined_text, topic, api_key)
                    else:
                        final_result = "(No analysis type chosen.)"
                if output_lang != "Deutsch":
                    lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                    target_lang = lang_map.get(output_lang, "English")
                    final_result = translate_text_openai(final_result, "German", target_lang, api_key)
                st.subheader("Compare-Mode Result:")
                st.write(final_result)
        # Single or multi-mode
        else:
            st.write("### Single or multi-mode (no outlier-check)")
            pdf_options = ["(Alle)"] + [f"{i+1}) {f.name}" for i, f in enumerate(uploaded_files)]
            selected_pdf = st.selectbox("Choose a PDF for single analysis or '(Alle)'", pdf_options)

            col_analysis, col_contradiction = st.columns(2)

            with col_analysis:
                if st.button("Start Analysis (Single Mode)"):
                    if selected_pdf == "(Alle)":
                        files_to_process = uploaded_files
                    else:
                        idx = pdf_options.index(selected_pdf) - 1
                        if idx < 0:
                            st.warning("No file selected.")
                            return
                        files_to_process = [uploaded_files[idx]]

                    final_result_text = []
                    for fpdf in files_to_process:
                        text_data = ""
                        if action != "Tabellen & Grafiken":
                            with st.spinner(f"Extracting text from {fpdf.name}..."):
                                text_data = analyzer.extract_text_from_pdf(fpdf)
                                if not text_data.strip():
                                    st.error(f"No text extracted from {fpdf.name}.")
                                    continue
                                st.session_state["paper_text"] = text_data[:15000]
                        result = ""
                        if action == "Zusammenfassung":
                            with st.spinner(f"Summarizing {fpdf.name}..."):
                                result = analyzer.summarize(text_data, api_key)
                        elif action == "Wichtigste Erkenntnisse":
                            with st.spinner(f"Extracting key findings from {fpdf.name}..."):
                                result = analyzer.extract_key_findings(text_data, api_key)
                        elif action == "Methoden & Techniken":
                            with st.spinner(f"Identifying methods in {fpdf.name}..."):
                                result = analyzer.identify_methods(text_data, api_key)
                        elif action == "Relevanz-Bewertung":
                            if not topic:
                                st.error("Please specify a topic!")
                                return
                            with st.spinner(f"Evaluating relevance for {fpdf.name}..."):
                                result = analyzer.evaluate_relevance(text_data, topic, api_key)
                        elif action == "Tabellen & Grafiken":
                            with st.spinner(f"Searching for tables/figures in {fpdf.name}..."):
                                # Implementation for table/figure extraction
                                # Then optionally we analyze them with GPT.
                                all_tables_text = []
                                try:
                                    with pdfplumber.open(fpdf) as pdf_:
                                        for page_number, page in enumerate(pdf_.pages, start=1):
                                            st.markdown(f"### Page {page_number} of {fpdf.name}")
                                            tables = page.extract_tables()
                                            if tables:
                                                st.markdown("**Tables on this page**")
                                                for table_idx, table_data in enumerate(tables, start=1):
                                                    if not table_data:
                                                        st.write("Empty table.")
                                                        continue
                                                    first_row = table_data[0]
                                                    data_rows = table_data[1:]
                                                    if not data_rows:
                                                        st.write("Header only.")
                                                        data_rows = table_data
                                                        first_row = [f"Col_{i}" for i in range(len(data_rows[0]))]
                                                    import pandas as pd
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
                                                        st.write("Warning: inconsistent column count.")
                                                        df = pd.DataFrame(table_data)
                                                    else:
                                                        df = pd.DataFrame(data_rows, columns=new_header)
                                                    st.write(f"**Table {table_idx}** in {fpdf.name}:")
                                                    st.dataframe(df)
                                                    table_str = df.to_csv(index=False)
                                                    all_tables_text.append(f"Page {page_number} - Table {table_idx}\n{table_str}\n")
                                            else:
                                                st.write("No tables on this page.")
                                            images = page.images
                                            if images:
                                                st.markdown("**Images/Figures on this page**")
                                                for img_index, img_dict in enumerate(images, start=1):
                                                    xref = img_dict.get("xref")
                                                    if xref is not None:
                                                        extracted_img = page.extract_image(xref)
                                                        if extracted_img:
                                                            image_data = extracted_img["image"]
                                                            image = Image.open(io.BytesIO(image_data))
                                                            st.write(f"**Image {img_index}** in {fpdf.name}:")
                                                            st.image(image, use_column_width=True)
                                            else:
                                                st.write("No images on this page.")
                                    # Full-text "Table" search
                                    st.markdown(f"### Full-text 'Table' search in {fpdf.name}")
                                    try:
                                        text_all_pages = ""
                                        with pdfplumber.open(fpdf) as pdf2:
                                            for pg in pdf2.pages:
                                                t_ = pg.extract_text() or ""
                                                text_all_pages += t_ + "\n"
                                        lines = text_all_pages.splitlines()
                                        matches = [ln for ln in lines if "Table" in ln]
                                        if matches:
                                            st.write("Lines containing 'Table':")
                                            for ln in matches:
                                                st.write(f"- {ln}")
                                        else:
                                            st.write("No mention of 'Table'.")
                                    except Exception as e2:
                                        st.warning(f"Error in full-text 'Table' search: {e2}")
                                    if len(all_tables_text) > 0:
                                        combined_tables_text = "\n".join(all_tables_text)
                                        if len(combined_tables_text) > 14000:
                                            combined_tables_text = combined_tables_text[:14000] + "..."
                                        gpt_prompt = (
                                            "Please analyze the following tables from a scientific PDF. "
                                            "Summarize the key insights and (if possible) give a short interpretation "
                                            "related to lifestyle and health genetics:\n\n"
                                            f"{combined_tables_text}"
                                        )
                                        import openai
                                        openai.api_key = api_key
                                        try:
                                            gpt_resp = openai.ChatCompletion.create(
                                                model=model,
                                                messages=[
                                                    {"role": "system", "content": "You are an expert in PDF table analysis."},
                                                    {"role": "user", "content": gpt_prompt}
                                                ],
                                                temperature=0.3,
                                                max_tokens=1000
                                            )
                                            result = gpt_resp.choices[0].message.content
                                        except Exception as e2:
                                            st.error(f"GPT table analysis error: {e2}")
                                            result = "(Error in GPT analysis.)"
                                    else:
                                        result = f"No tables found in {fpdf.name}."
                                except Exception as e_:
                                    st.error(f"Error in {fpdf.name}: {str(e_)}")
                                    result = f"(Error in {fpdf.name})"
                        if action != "Tabellen & Grafiken" and result:
                            if output_lang != "Deutsch":
                                lang_map = {"Englisch": "English", "Portugiesisch": "Portuguese", "Serbisch": "Serbian"}
                                target_lang = lang_map.get(output_lang, "English")
                                result = translate_text_openai(result, "German", target_lang, api_key)
                        final_result_text.append(f"**Result for {fpdf.name}:**\n\n{result}")

                    st.subheader("Result of (Multi) Analysis (Single Mode):")
                    combined_output = "\n\n---\n\n".join(final_result_text)
                    st.markdown(combined_output)

            with col_contradiction:
                st.write("Contradiction Analysis (Uploaded Papers)")
                if st.button("Start Contradiction Analysis"):
                    if "paper_texts" not in st.session_state or not st.session_state["paper_texts"]:
                        st.session_state["paper_texts"] = {}
                        for upf in uploaded_files:
                            t_ = analyzer.extract_text_from_pdf(upf)
                            if t_.strip():
                                st.session_state["paper_texts"][upf.name] = t_
                    paper_texts = st.session_state["paper_texts"]
                    if not paper_texts:
                        st.error("No texts for contradiction analysis.")
                        return
                    with st.spinner("Analyzing uploaded papers for commonalities & contradictions..."):
                        result_json_str = analyze_papers_for_commonalities_and_contradictions(
                            pdf_texts=paper_texts,
                            api_key=api_key,
                            model=model,
                            method_choice="ContraCrow" if analysis_method == "ContraCrow" else "Standard"
                        )
                        st.subheader("Result (JSON)")
                        st.code(result_json_str, language="json")
                        try:
                            data_js = json.loads(result_json_str)
                            common = data_js.get("commonalities", [])
                            contras = data_js.get("contradictions", [])
                            st.write("## Commonalities")
                            if common:
                                for c in common:
                                    st.write(f"- {c}")
                            else:
                                st.info("No commonalities found.")
                            st.write("## Contradictions")
                            if contras:
                                for i, cobj in enumerate(contras, start=1):
                                    st.write(f"Contradiction {i}:")
                                    st.write(f"- **Paper A**: {cobj.get('paperA')} => {cobj.get('claimA')}")
                                    st.write(f"- **Paper B**: {cobj.get('paperB')} => {cobj.get('claimB')}")
                                    st.write(f"  Reason: {cobj.get('reason','(none)')}")
                            else:
                                st.info("No contradictions found.")
                        except Exception as e:
                            st.warning(f"GPT output is not valid JSON. Error: {e}")
    else:
        if not api_key:
            st.warning("Please provide an OpenAI API Key.")
        elif not uploaded_files:
            st.info("Please upload one or more PDF files.")

    st.write("---")
    st.write("## All Analyses & Excel Export (Multi-PDF)")

    if "excel_downloads" not in st.session_state:
        st.session_state["excel_downloads"] = []

    if uploaded_files and api_key:
        if st.button("Perform All Analyses & Save to Excel (Multi)"):
            st.session_state["excel_downloads"].clear()
            with st.spinner("Analyzing all uploaded PDFs for Excel..."):
                if compare_mode:
                    if not st.session_state["relevant_papers_compare"]:
                        paper_map_ = {}
                        for fpdf in uploaded_files:
                            txt__ = analyzer.extract_text_from_pdf(fpdf)
                            if txt__.strip():
                                paper_map_[fpdf.name] = txt__
                        if not paper_map_:
                            st.error("No usable papers.")
                            return
                        relevant_papers_auto, discovered_theme_auto = do_outlier_logic(paper_map_)
                        st.session_state["relevant_papers_compare"] = relevant_papers_auto
                        st.session_state["theme_compare"] = discovered_theme_auto
                    relevant_list_for_excel = st.session_state["relevant_papers_compare"] or []
                    if not relevant_list_for_excel:
                        st.error("No relevant papers after outlier-check for Excel.")
                        return
                    selected_files_for_excel = [f for f in uploaded_files if f.name in relevant_list_for_excel]
                else:
                    selected_files_for_excel = uploaded_files

                for fpdf in selected_files_for_excel:
                    text_ = analyzer.extract_text_from_pdf(fpdf)
                    if not text_.strip():
                        st.error(f"No text from {fpdf.name}, skipping.")
                        continue

                    summary_de = analyzer.summarize(text_, api_key)
                    key_findings_de = analyzer.extract_key_findings(text_, api_key)
                    # The final Excel is in English
                    summary_en = translate_text_openai(summary_de, "German", "English", api_key)
                    key_findings_en = translate_text_openai(key_findings_de, "German", "English", api_key)

                    main_theme_excel = st.session_state.get("theme_compare", "N/A")
                    if not compare_mode and theme_mode == "Manuell":
                        main_theme_excel = user_defined_theme or "N/A"

                    if not topic:
                        relevance_de = "(No topic => no relevance scoring)"
                        relevance_en = relevance_de
                    else:
                        relevance_de = analyzer.evaluate_relevance(text_, topic, api_key)
                        relevance_en = translate_text_openai(relevance_de, "German", "English", api_key)

                    methods_de = analyzer.identify_methods(text_, api_key)
                    methods_en = translate_text_openai(methods_de, "German", "English", api_key)

                    ergebnisse_de, schlussfolgerungen_de = split_summary(summary_de)
                    ergebnisse_en = translate_text_openai(ergebnisse_de, "German", "English", api_key)
                    schlussfolgerungen_en = translate_text_openai(schlussfolgerungen_de, "German", "English", api_key)

                    cohort_data_ = parse_cohort_info(summary_de)
                    c_size = cohort_data_.get("study_size", "")
                    c_origin = cohort_data_.get("origin", "")
                    if c_size or c_origin:
                        c_info = (c_size + (", " + c_origin if c_origin else "")).strip(", ")
                    else:
                        c_info = ""
                    # Already in English if found. If we want to ensure, do a short translation:
                    c_info_en = translate_text_openai(c_info, "German", "English", api_key) if c_info else ""

                    # Gene + rs detection
                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    mtxt = re.search(pattern_obvious, text_)
                    gene_via_text = mtxt.group(1) if mtxt else ""

                    rs_pat = r"(rs\d+)"
                    found_rs_match_ = re.search(rs_pat, text_)
                    rs_num = found_rs_match_.group(1) if found_rs_match_ else ""

                    # Searching potential genotype references
                    genotype_regex = r"\b([ACGT]{2,3})\b"
                    lines__ = text_.split("\n")
                    found_pairs__ = []
                    for line__ in lines__:
                        matches__ = re.findall(genotype_regex, line__)
                        if matches__:
                            for gm in matches__:
                                found_pairs__.append((gm, line__.strip()))
                    unique_geno_pairs__ = []
                    for gp__ in found_pairs__:
                        if gp__ not in unique_geno_pairs__:
                            unique_geno_pairs__.append(gp__)

                    # In Excel, we want up to 3 genotypes with freq info. We use our AlleleFrequencyFinder -> correct H-W logic
                    aff = AlleleFrequencyFinder()
                    # We'll store 'Global population frequency' for a single genotype, or "No data," etc.
                    # If we want multiple genotype checks, we can do so. For simplicity, we do first 3.
                    # We'll write them in rows 10,11,12 in English.

                    # Pub year from text
                    pub_year_match_ = re.search(r"\b(20[0-9]{2})\b", text_)
                    year_for_excel = pub_year_match_.group(1) if pub_year_match_ else "n/a"

                    # PMIDs
                    pmid_pattern_ = re.compile(r"\bPMID:\s*(\d+)\b", re.IGNORECASE)
                    pmid_match_ = pmid_pattern_.search(text_)
                    pmid_found_ = pmid_match_.group(1) if pmid_match_ else "n/a"
                    doi_final_, link_pubmed_ = ("n/a", "")
                    if pmid_found_ != "n/a":
                        doi_final_, link_pubmed_ = fetch_pubmed_doi_and_link(pmid_found_)

                    # Now load Excel template. All entries in ENGLISH
                    try:
                        wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                    except FileNotFoundError:
                        st.error("Template 'vorlage_paperqa2.xlsx' not found!")
                        return
                    ws = wb.active

                    ws["D2"].value = main_theme_excel
                    ws["J2"].value = datetime.datetime.now().strftime("%Y-%m-%d")

                    ws["D5"].value = gene_via_text
                    ws["D6"].value = rs_num

                    # Up to 3 genotype lines
                    genotype_entries_ = unique_geno_pairs__[:3]
                    for i_ in range(3):
                        row_idx_ = 10 + i_
                        if i_ < len(genotype_entries_):
                            genotype_str_ = genotype_entries_[i_][0]
                            ws[f"D{row_idx_}"].value = genotype_str_
                            if rs_num and genotype_str_:
                                freq_text = aff.build_freq_info_text(rs_num, genotype_str_)
                            else:
                                freq_text = f"No genotype frequency for {genotype_str_}"
                            ws[f"E{row_idx_}"].value = freq_text
                        else:
                            ws[f"D{row_idx_}"] = ""
                            ws[f"E{row_idx_}"] = ""

                    ws["C20"].value = year_for_excel
                    ws["D20"].value = c_info_en
                    ws["E20"].value = key_findings_en
                    ws["G21"].value = ergebnisse_en
                    ws["G22"].value = schlussfolgerungen_en

                    # PubMed info
                    ws["J21"].value = pmid_found_
                    ws["J22"].value = link_pubmed_
                    ws["I22"].value = doi_final_

                    output_buffer_ = io.BytesIO()
                    wb.save(output_buffer_)
                    output_buffer_.seek(0)

                    xlsx_name_ = f"analysis_{fpdf.name.replace('.pdf','')}.xlsx"
                    st.session_state["excel_downloads"].append({
                        "label": f"Download Excel for {fpdf.name}",
                        "data": output_buffer_.getvalue(),
                        "file_name": xlsx_name_
                    })

    if "excel_downloads" in st.session_state and st.session_state["excel_downloads"]:
        st.write("## Generated Excel Downloads:")
        for dl in st.session_state["excel_downloads"]:
            st.download_button(
                label=dl["label"],
                data=dl["data"],
                file_name=dl["file_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.write("---")
    st.write("## Single Analysis of ChatGPT-Scored Papers")

    if st.button("Perform Scoring now"):
        if "search_results" in st.session_state and st.session_state["search_results"]:
            codewords_str = st.session_state.get("codewords", "")
            selected_genes = st.session_state.get("selected_genes", [])
            scored_list = chatgpt_online_search_with_genes(
                papers=st.session_state["search_results"],
                codewords=codewords_str,
                genes=selected_genes,
                top_k=200
            )
            st.session_state["scored_list"] = scored_list
            st.success("Scored papers saved in st.session_state['scored_list'].")
        else:
            st.info("No previous search results. Cannot score.")

    if "scored_list" not in st.session_state or not st.session_state["scored_list"]:
        st.info("No scored papers. Click 'Perform Scoring now' first.")
        return

    st.subheader("Single analysis for ChatGPT-scored papers")
    scored_titles = [paper["Title"] for paper in st.session_state["scored_list"]]
    chosen_title = st.selectbox(
        "Choose a paper from the scoring list:",
        options=["(No selection)"] + scored_titles
    )

    analysis_choice_for_scored_paper = st.selectbox(
        "Which analysis do you want to do?",
        ["(None)", "Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"]
    )

    if chosen_title != "(No selection)":
        selected_paper = next((p for p in st.session_state["scored_list"] if p["Title"] == chosen_title), None)
        if selected_paper:
            st.write("**Title:**", selected_paper.get("Title", "n/a"))
            st.write("**Source:**", selected_paper.get("Source", "n/a"))
            st.write("**PubMed ID:**", selected_paper.get("PubMed ID", "n/a"))
            st.write("**Year:**", selected_paper.get("Year", "n/a"))
            st.write("**Publisher:**", selected_paper.get("Publisher", "n/a"))
            st.write("**Abstract:**")
            abstract = selected_paper.get("Abstract", "")
            if abstract.strip():
                st.markdown(f"> {abstract}")
            else:
                st.warning("No abstract available.")
            if st.button("Analyze this paper now"):
                if not abstract.strip():
                    st.error("No abstract, cannot analyze.")
                    return
                local_analyzer = PaperAnalyzer(model=model)
                if analysis_choice_for_scored_paper == "Zusammenfassung":
                    res_de = local_analyzer.summarize(abstract, api_key)
                    res_en = translate_text_openai(res_de, "German", "English", api_key)
                    st.write("### Analysis Result (English):")
                    st.write(res_en)
                elif analysis_choice_for_scored_paper == "Wichtigste Erkenntnisse":
                    res_de = local_analyzer.extract_key_findings(abstract, api_key)
                    res_en = translate_text_openai(res_de, "German", "English", api_key)
                    st.write("### Analysis Result (English):")
                    st.write(res_en)
                elif analysis_choice_for_scored_paper == "Methoden & Techniken":
                    res_de = local_analyzer.identify_methods(abstract, api_key)
                    res_en = translate_text_openai(res_de, "German", "English", api_key)
                    st.write("### Analysis Result (English):")
                    st.write(res_en)
                elif analysis_choice_for_scored_paper == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Please enter a topic (see sidebar).")
                        return
                    res_de = local_analyzer.evaluate_relevance(abstract, topic, api_key)
                    res_en = translate_text_openai(res_de, "German", "English", api_key)
                    st.write("### Analysis Result (English):")
                    st.write(res_en)
                else:
                    st.info("No valid analysis selected.")
        else:
            st.warning("Paper not found (unexpected error).")

    st.write("---")
    st.header("PaperQA Multi-Paper Analyzer: Commonalities & Contradictions (Scored Papers)")
    if st.button("Analyze (Scored Papers) now"):
        if "scored_list" in st.session_state and st.session_state["scored_list"]:
            paper_texts = {}
            for paper in st.session_state["scored_list"]:
                title = paper.get("Title", "Unnamed")
                abstract = paper.get("Abstract", "")
                if abstract.strip():
                    paper_texts[title] = abstract
                else:
                    st.warning(f"No abstract for {title}.")
            if not paper_texts:
                st.error("No texts for analysis.")
                return
            with st.spinner("Analyzing scored papers for commonalities & contradictions..."):
                result_json_str = analyze_papers_for_commonalities_and_contradictions(
                    pdf_texts=paper_texts,
                    api_key=api_key,
                    model=model,
                    method_choice="ContraCrow" if analysis_method == "ContraCrow" else "Standard"
                )
                st.subheader("Result (JSON)")
                st.code(result_json_str, language="json")
                try:
                    data_js = json.loads(result_json_str)
                    common = data_js.get("commonalities", [])
                    contras = data_js.get("contradictions", [])
                    st.write("## Commonalities")
                    if common:
                        for c in common:
                            st.write(f"- {c}")
                    else:
                        st.info("No commonalities found.")
                    st.write("## Contradictions")
                    if contras:
                        for i, cobj in enumerate(contras, start=1):
                            st.write(f"Contradiction {i}:")
                            st.write(f"- **Paper A**: {cobj.get('paperA')} => {cobj.get('claimA')}")
                            st.write(f"- **Paper B**: {cobj.get('paperB')} => {cobj.get('claimB')}")
                            st.write(f"  Reason: {cobj.get('reason','(none)')}")
                    else:
                        st.info("No contradictions found.")
                except Exception as e:
                    st.warning("Could not parse GPT output as valid JSON.")
        else:
            st.error("No scored papers. Please score them first.")

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
    """
    Simple chat example:
    Uses any paper text in st.session_state (paper_text) as context if available.
    """
    api_key = st.session_state.get("api_key", "")
    paper_text = st.session_state.get("paper_text", "")
    if not api_key:
        return f"(No API Key) Echo: {question}"
    if not paper_text.strip():
        sys_msg = "You are a helpful assistant for general questions."
    else:
        sys_msg = (
            "You are a helpful assistant, and here is a paper as context:\n\n"
            + paper_text[:12000] + "\n\n"
            "Please use it to answer questions as expertly as possible."
        )
    import openai
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
        return f"OpenAI error: {e}"

def main():
    """
    Main entry point:
    Left side: Navigation
    Right side: Chatbot
    """
    col_left, col_right = st.columns([4, 1])
    with col_left:
        page_fn = sidebar_module_navigation()
        if page_fn:
            page_fn()
    with col_right:
        st.subheader("Chatbot")
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []
        user_input = st.text_input("Your question here", key="chatbot_right_input")
        if st.button("Send (Chat)", key="chatbot_right_send"):
            if user_input.strip():
                st.session_state["chat_history"].append(("user", user_input))
                bot_answer = answer_chat(user_input)
                st.session_state["chat_history"].append(("bot", bot_answer))

        # Chat display
        st.markdown(
            """
            <style>
            .scrollable-chat {
                max-height: 400px;
                overflow-y: auto;
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
        st.markdown('<div class="scrollable-chat" id="chat-container">', unsafe_allow_html=True)
        for role, msg_text in st.session_state["chat_history"]:
            if role == "user":
                st.markdown(
                    f'<div class="message user-message"><strong>You:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="message assistant-message"><strong>Bot:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
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
