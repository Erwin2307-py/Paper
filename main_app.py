import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

from modules.online_api_filter import module_online_api_filter

# -----------------------------------------
# Login-Funktion mit [login]-Schlüssel
# -----------------------------------------
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

# Falls noch nicht im Session State: Standard auf False setzen
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# Prüfe den Login-Status. Wenn NICHT eingeloggt, zeige Login-Seite an, dann stop.
if not st.session_state["logged_in"]:
    login()
    st.stop()

# -----------------------------------------
# Wenn wir hier ankommen, ist man eingeloggt
# -----------------------------------------

# ------------------------------------------------------------
# EINMALIGE set_page_config(...) hier ganz am Anfang
# ------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

################################################################################
# 1) Gemeinsame Funktionen & Klassen (unverändert)
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
# PubMed Connection Check + (Basis) Search (unverändert)
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
# Europe PMC Connection Check + (Basis) Search (unverändert)
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
# OpenAlex API Communication (unverändert)
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
# Google Scholar (Basis) Test (unverändert)
################################################################################

from scholarly import scholarly

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


################################################################################
# Semantic Scholar API Communication (unverändert)
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
# 2) Neues Modul: "module_excel_online_search" (unverändert)
################################################################################
# [unverändert...]

################################################################################
# 3) Restliche Module + Seiten (Pages) (unverändert)
################################################################################

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


################################################################################
# 4) PAPER ANALYZER (unverändert) + Load Env/OPENAI key
################################################################################
import os
import PyPDF2
import openai
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model
    
    def extract_text_from_pdf(self, pdf_file):
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    def analyze_with_openai(self, text, prompt_template, api_key):
        if len(text) > 15000:
            text = text[:15000] + "..."
        
        prompt = prompt_template.format(text=text)
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Experte für die Analyse wissenschaftlicher Paper, "
                        "besonders im Bereich Side-Channel Analysis."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content
    
    def summarize(self, text, api_key):
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere es in: Hintergrund, Methodik, "
            "Ergebnisse und Schlussfolgerungen. Verwende maximal 500 Wörter:\n\n{text}"
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


################################################################################
# NEU: Die Klasse AlleleFrequencyFinder (aus deinem Snippet) + Integration
################################################################################

import time
import sys
import json
from typing import Dict, Any, Optional

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

################################################################################
# 5) PAGE "Analyze Paper" - Hier steht die neue Gen-Logik: Erst "offensichtlicher Hinweis", dann Excel.
################################################################################
def page_analyze_paper():
    """
    Seite "Analyze Paper": ruft direkt den PaperAnalyzer auf.
    * Zuerst versuchen wir, aus dem Text "in the XYZ Gene" zu parsen (z.B. CYP24A1).
    * Wenn das nicht klappt, fallback: wir lesen 'vorlage_gene.xlsx' und suchen alle Genes.
    """
    st.title("Analyze Paper - Integriert")

    st.sidebar.header("Einstellungen - PaperAnalyzer")
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    model = st.sidebar.selectbox("OpenAI-Modell",
                                 ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
                                 index=0)
    action = st.sidebar.radio("Analyseart",
                              ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
                              index=0)
    topic = st.sidebar.text_input("Thema für Relevanz-Bewertung (falls relevant)")

    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")

    analyzer = PaperAnalyzer(model=model)

    # 1) EINZELNE ANALYSE VIA RADIO-Knopf
    if uploaded_file and api_key:
        if st.button("Analyse starten"):
            with st.spinner("Extrahiere Text aus PDF..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Kein Text extrahierbar (evtl. gescanntes PDF ohne OCR).")
                    st.stop()
                st.success("Text wurde erfolgreich extrahiert!")

            with st.spinner(f"Führe {action}-Analyse durch..."):
                if action == "Zusammenfassung":
                    result = analyzer.summarize(text, api_key)
                elif action == "Wichtigste Erkenntnisse":
                    result = analyzer.extract_key_findings(text, api_key)
                elif action == "Methoden & Techniken":
                    result = analyzer.identify_methods(text, api_key)
                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Bitte Thema angeben für die Relevanz-Bewertung!")
                        st.stop()
                    result = analyzer.evaluate_relevance(text, topic, api_key)

                st.subheader("Ergebnis der Analyse")
                st.markdown(result)
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_file:
            st.info("Bitte eine PDF-Datei hochladen!")

    # 2) ALLE ANALYSEN & EXCEL-SPEICHERN
    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe")
    user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")

    if uploaded_file and api_key:
        if st.button("Alle Analysen durchführen & in Excel speichern"):
            with st.spinner("Analysiere alles..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Kein Text extrahierbar (evtl. gescanntes PDF ohne OCR).")
                    st.stop()

                # GPT-Analysen:
                summary_result = analyzer.summarize(text, api_key)
                key_findings_result = analyzer.extract_key_findings(text, api_key)
                methods_result = analyzer.identify_methods(text, api_key)
                if not topic:
                    st.error("Bitte 'Thema für Relevanz-Bewertung' angeben!")
                    st.stop()
                relevance_result = analyzer.evaluate_relevance(text, topic, api_key)
                final_relevance = f"{relevance_result}\n\n[Manuelle Bewertung: {user_relevance_score}]"

                import openpyxl
                import io
                import datetime

                # --------------------------------------------------------------
                # 1) "Offensichtlicher Hinweis" im Text: "in the XYZ Gene"
                # --------------------------------------------------------------
                gene_via_text = None
                pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                match_text = re.search(pattern_obvious, text)
                if match_text:
                    gene_via_text = match_text.group(1)

                if gene_via_text:
                    found_gene = gene_via_text
                else:
                    # fallback: 'vorlage_gene.xlsx'
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

                try:
                    wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                except FileNotFoundError:
                    st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                    st.stop()

                ws = wb.active

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

                output = io.BytesIO()
                wb.save(output)
                output.seek(0)

            st.success("Alle Analysen abgeschlossen – Excel-Datei erstellt und Felder befüllt!")
            st.download_button(
                label="Download Excel",
                data=output,
                file_name="analysis_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

################################################################################
# NEUE Funktion: KI-Chatbot
################################################################################

def page_chatbot():
    import openai
    from openai import OpenAI

    st.set_page_config(page_title="KI-Chatbot", page_icon="🤖")

    # Styling für den Chat
    st.markdown("""
    <style>
        .stChatMessage {
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }
        .stChatMessage[data-role="user"] {
            background-color: #e6f7ff;
        }
        .stChatMessage[data-role="assistant"] {
            background-color: #f0f0f0;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("🤖 Mein KI-Chatbot")

    # OpenAI API-Key aus Streamlit Secrets
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if api_key is None:
        api_key = st.text_input("OpenAI API-Key eingeben:", type="password")
        if not api_key:
            st.warning("Bitte gib deinen OpenAI API-Key ein, um den Chatbot zu nutzen.")
            return

    client = OpenAI(api_key=api_key)

    model_options = ["gpt-3.5-turbo", "gpt-4o"]
    selected_model = st.sidebar.selectbox("Modell auswählen:", model_options)

    temperature = st.sidebar.slider("Kreativität (Temperature):", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
    max_tokens = st.sidebar.slider("Maximale Antwortlänge:", min_value=50, max_value=4000, value=1000, step=50)

    system_prompt = st.sidebar.text_area(
        "System-Prompt (Anweisungen für den Chatbot):",
        value="Du bist ein hilfreicher Assistent, der präzise und freundliche Antworten gibt.",
        height=100
    )

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Hallo! Wie kann ich dir heute helfen?"}
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Schreibe deine Nachricht..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            messages_for_api = [
                {"role": "system", "content": system_prompt}
            ] + st.session_state.messages
            
            try:
                stream = client.chat.completions.create(
                    model=selected_model,
                    messages=[{"role": m["role"], "content": m["content"]} for m in messages_for_api],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)

            except Exception as e:
                st.error(f"Fehler bei der Kommunikation mit OpenAI: {str(e)}")
                full_response = "Entschuldigung, es gab ein Problem bei der Generierung der Antwort."
                message_placeholder.markdown(full_response)
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})

    with st.sidebar.expander("Info", expanded=False):
        st.markdown("""
        ## Über diesen Chatbot

        Dieser Chatbot nutzt das OpenAI-API und ist mit Streamlit erstellt.

        1. API-Key eintragen
        2. Modell & Optionen wählen
        3. Chatten!
        """)

################################################################################
# 6) Sidebar Module Navigation & Main (unverändert)
################################################################################

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        # "4) Paper Selection": page_paper_selection,
        # "5) Analysis & Evaluation": page_analysis,
        # "6) Extended Topics": page_extended_topics,
        # "7) PaperQA2": page_paperqa2,
        # "8) Excel Online Search": page_excel_online_search,
        # "9) Selenium Q&A": page_selenium_qa,

        # Dein "Analyze Paper" wie gehabt
        "Analyze Paper": page_analyze_paper,

        # NEUER MENÜPUNKT Chatbot:
        "KI-Chatbot": page_chatbot
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
