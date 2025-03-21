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
# PaperAnalyzer-Klasse siehe oben
# AlleleFrequencyFinder-Klasse siehe oben
# Hilfsfunktionen split_summary/parse_cohort_info siehe oben
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

    # Compare Mode
    compare_mode = st.sidebar.checkbox("Alle Paper gemeinsam vergleichen (Outlier ausschließen)?")

    # NEU: Radio: Hauptthema => 'manuell' oder 'GPT'
    theme_mode = st.sidebar.radio(
        "Hauptthema bestimmen",
        ["Manuell", "GPT"]
    )

    action = st.sidebar.radio(
        "Analyseart",
        [
            "Zusammenfassung", 
            "Wichtigste Erkenntnisse", 
            "Methoden & Techniken", 
            "Relevanz-Bewertung",
            "Tabellen & Grafiken"
        ],
        index=0
    )
    
    # Manuelles Thema, falls relevant
    user_defined_theme = ""
    if theme_mode == "Manuell":
        user_defined_theme = st.sidebar.text_input("Manuelles Hauptthema (bei Compare-Mode)")

    topic = st.sidebar.text_input("Thema für Relevanz-Bewertung (falls relevant)")
    output_lang = st.sidebar.selectbox(
        "Ausgabesprache",
        ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"],
        index=0
    )

    uploaded_files = st.file_uploader("PDF-Dateien hochladen", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]

    if "relevant_papers_compare" not in st.session_state:
        st.session_state["relevant_papers_compare"] = None
    if "theme_compare" not in st.session_state:
        st.session_state["theme_compare"] = ""

    def do_outlier_logic(paper_map: dict) -> (list, str):
        """Gibt (relevantPaperList, discoveredTheme) zurück."""
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
    {{
      "filename": "...",
      "relevant": true/false,
      "reason": "Kurzer Grund"
    }}
  ]
}}

Nur das JSON, ohne weitere Erklärungen.

[{big_snippet}]
"""
            try:
                openai.api_key = api_key
                scope_resp = openai.chat.completions.create(
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
                rel = p.get("relevant", False)
                reason = p.get("reason","(none)")
                if rel:
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Begründung: {reason}")
                else:
                    st.warning(f"{fname} => NICHT relevant. Begründung: {reason}")

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
    {{"filename":"...","relevant":true/false,"reason":"Kurzer Grund"}}
  ]
}}

Bitte NUR dieses JSON liefern, ohne weitere Erklärungen:

[{big_snippet}]
"""
            try:
                openai.api_key = api_key
                scope_resp = openai.chat.completions.create(
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
                rel = p.get("relevant", False)
                reason = p.get("reason","(none)")
                if rel:
                    relevant_papers_local.append(fname)
                    st.success(f"{fname} => relevant. Begründung: {reason}")
                else:
                    st.warning(f"{fname} => NICHT relevant. Begründung: {reason}")

            return (relevant_papers_local, main_theme)

    # ---------------------------
    # Haupt-Analyse
    # ---------------------------
    if uploaded_files and api_key:
        if compare_mode:
            st.write("### Vergleichsmodus: Outlier-Paper ausschließen")

            if st.button("Vergleichs-Analyse starten"):
                # 1) ALLE Papertexte sammeln
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

                # 2) Kombiniere relevanten Papertext
                combined_text = ""
                for rp in relevant_papers:
                    combined_text += f"\n=== {rp} ===\n{paper_map[rp]}"

                # 3) Führe gewählte Analyse durch
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
                    lang_map = {
                        "Englisch": "English",
                        "Portugiesisch": "Portuguese",
                        "Serbisch": "Serbian"
                    }
                    target_lang = lang_map.get(output_lang, "English")
                    final_result = translate_text_openai(final_result, "German", target_lang, api_key)

                st.subheader("Ergebnis des Compare-Mode:")
                st.write(final_result)

        else:
            # Einzel- oder Multi-Modus ohne Compare
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
                                                all_tables_text.append(
                                                    f"Seite {page_number} - Tabelle {table_idx}\n{table_str}\n"
                                                )
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
                                                        image = Image.open(io.BytesIO(image_data))
                                                        st.write(f"**Bild {img_index}** in {fpdf.name}:")
                                                        st.image(image, use_column_width=True)
                                                    else:
                                                        st.write(f"Bild {img_index} konnte nicht extrahiert werden.")
                                        else:
                                            st.write("Keine Bilder hier.")

                                # Zusätzliche Suche "Table" im Volltext
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
                                        "Fasse die wichtigsten Erkenntnisse zusammen und gib (wenn möglich) eine "
                                        "kurze Interpretation in Bezug auf Lifestyle und Health Genetics:\n\n"
                                        f"{combined_tables_text}"
                                    )
                                    try:
                                        openai.api_key = api_key
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
                combined_output = "\n\n---\n\n".join(final_result_text)
                st.markdown(combined_output)

    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_files:
            st.info("Bitte eine oder mehrere PDF-Dateien hochladen!")

    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe (Multi-PDF)")

    user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")

    # ------------------------------------------------------------------
    # NEU: Excel-Ausgabe in VORLAGE an den FIXEN Zellen (D5, D6, etc.)
    # ------------------------------------------------------------------
    if uploaded_files and api_key:
        if st.button("Alle Analysen durchführen & in Excel (Vorlage) speichern"):
            with st.spinner("Analysiere alle hochgeladenen PDFs (Vorlage-Fix)..."):
                import openpyxl
                import datetime

                try:
                    wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                except FileNotFoundError:
                    st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                    st.stop()

                # Wir gehen Paper für Paper durch und "verschieben" uns um 5 Zeilen
                # oder Spalten, je Paper => laut Vorgaben
                # Die User-Anforderung: 
                #   - gene name => D5
                #   - rs => D6
                #   - genotypes => D10, E10 => freq, dann D11/E11, D12/E12
                #   - date of publication => C20
                #   - study size => D20
                #   - key findings => E20
                #   - results => G21
                #   - conclusion => G22
                #   - summary paper2 => E25, usw...
                #
                # Realisieren wir nun: 
                #   * Paper 1 => already in lines 5.. => that means no shift
                #   * Paper 2 => shift by 5 rows => so "D5" -> "D10"? 
                #   Actually the user specifically said "Paper2 => E25"? 
                #   It's somewhat contradictory. We do a step of +5 for the "Summary block".
                #
                # => We'll interpret: Each new paper will shift the "block" by +25 rows
                #    so that "Paper2" can have "D(5+25)=D30" and so on, or we do the SHIFT
                #    in the *rows*. 
                # To keep it simpler, let's do a SHIFT for each new paper, e.g. if the "block"
                # for Paper 1 is row offset=0, for Paper 2 is row offset=25, Paper 3 is +50, etc.

                # Hilfs-Funktion: FillCells
                def fill_paper_in_template(ws, offset, paper_data):
                    """
                    offset = multiple of 25 => row shift
                    paper_data => dict with needed fields
                    We'll fill:
                      D5 => gene
                      D6 => rs
                      D10 => genotype1
                      E10 => freq1
                      D11 => genotype2
                      E11 => freq2
                      D12 => genotype3
                      E12 => freq3
                      ...
                      C20 => date_of_publication
                      D20 => study_size
                      E20 => key_findings
                      G21 => results
                      G22 => conclusion
                    but each row is offset by 'offset'.
                    """
                    # So row(5+offset) col D => gene, etc.
                    # We'll parse out the fields from paper_data
                    # Paper data keys:
                    # 'gene', 'rs', 'genotypes' => list of (geno, freq),
                    # 'date_of_publication', 'study_size', 'key_findings', 'results', 'conclusion'

                    # gene => ws["D5 + offset"]
                    # We'll do rowBase = 5 + offset, col D is 4 => ws.cell(rowBase, 4)
                    rowBase = 5 + offset
                    # D = 4, E=5, G=7, C=3
                    # We'll define a helper for cell col letter => colIndex
                    def col_to_index(letter):
                        return ord(letter.upper()) - ord('A') + 1

                    # gene
                    ws.cell(row=rowBase, column=col_to_index("D")).value = paper_data.get("gene","")
                    # rs
                    ws.cell(row=rowBase+1, column=col_to_index("D")).value = paper_data.get("rs","")

                    # genotypes => up to 3
                    # D10/E10 => rowBase+5 => row(10 + offset)
                    # D11/E11 => rowBase+6
                    # D12/E12 => rowBase+7
                    # each is (geno, freq)
                    gList = paper_data.get("genotypes", [])
                    for i, gf in enumerate(gList[:3], start=0):
                        row_geno = rowBase + 5 + i
                        geno, freq = gf
                        ws.cell(row=row_geno, column=col_to_index("D")).value = geno
                        ws.cell(row=row_geno, column=col_to_index("E")).value = freq

                    # date_of_publication => C20 => rowBase+15, col=3
                    ws.cell(row=rowBase+15, column=3).value = paper_data.get("date_of_publication","")

                    # study_size => D20 => rowBase+15, col=4
                    ws.cell(row=rowBase+15, column=4).value = paper_data.get("study_size","")

                    # key_findings => E20 => rowBase+15, col=5
                    ws.cell(row=rowBase+15, column=5).value = paper_data.get("key_findings","")

                    # results => G21 => rowBase+16, col=7
                    ws.cell(row=rowBase+16, column=7).value = paper_data.get("results","")

                    # conclusion => G22 => rowBase+17, col=7
                    ws.cell(row=rowBase+17, column=7).value = paper_data.get("conclusion","")

                # check if compare_mode => relevant or not
                if compare_mode:
                    if not st.session_state["relevant_papers_compare"]:
                        # user forgot to do "Vergleichs-Analyse starten"
                        st.warning("Compare-Mode: Führe erst 'Vergleichs-Analyse starten' aus!")
                        # wir machen es notfalls auto
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

                    relevant_list_for_excel = st.session_state["relevant_papers_compare"] or []
                    if not relevant_list_for_excel:
                        st.error("Keine relevanten Paper nach Outlier-Check für Excel.")
                        return
                    selected_files_for_excel = [f for f in uploaded_files if f.name in relevant_list_for_excel]
                else:
                    selected_files_for_excel = uploaded_files

                rowOffset = 0
                ws = wb.active  # Wir nehmen das aktive Sheet
                # Das Template hat Paper1-Felder an row=5.. => offset=0
                # Paper2 => offset=25, Paper3 => offset=50, etc.

                for i, fpdf in enumerate(selected_files_for_excel):
                    paper_data = {}
                    # 1) extract text
                    text = analyzer.extract_text_from_pdf(fpdf)
                    if not text.strip():
                        st.error(f"Kein Text aus {fpdf.name} extrahierbar. Überspringe ...")
                        continue

                    # 2) parse needed fields
                    #    => gene, rs, up to 3 genotypes w/ freq, date_of_publication, study_size, key_findings, results, conclusion
                    #    For date_of_publication we can do "n/a" or guess from the text?
                    #    We'll do a naive approach for date_of_publication => "2023-01-01" or "Unknown"
                    #    or we can parse from text ...
                    # We'll do naive approach: we store "n/a" or the user's "year" from the "subject"

                    # Suppose no real date => "n/a"
                    # Suppose no real conclusion => we do "No separate conclusion"

                    # We do minimal analysis or re-use the partial results from the "summarize" + "extract_key_findings"
                    summary_result = analyzer.summarize(text, api_key)
                    key_findings_result = analyzer.extract_key_findings(text, api_key)
                    # we define "results" as maybe the "Ergebnisse" splitted from summary
                    ergebnisse, schlussf = split_summary(summary_result)

                    # parse cohort => e.g. parse_cohort_info => yields study_size
                    cohort_info = parse_cohort_info(summary_result)
                    study_size = cohort_info.get("study_size","(no data)")

                    # date_of_publication => let's do "2023" as fallback
                    date_of_pub = "n/a"

                    # gene => maybe "in the X gene"
                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    match_text = re.search(pattern_obvious, text)
                    gene_name = match_text.group(1) if match_text else "n/a"

                    # find rs => "rs\d+"
                    rs_pat = r"(rs\d+)"
                    found_rs_match = re.search(rs_pat, text)
                    rs_num = found_rs_match.group(1) if found_rs_match else "n/a"

                    # genotype => up to 3
                    genotype_regex = r"\b([ACGT]{2,3})\b"
                    lines = text.split("\n")
                    found_pairs = []
                    for line in lines:
                        matches = re.findall(genotype_regex, line)
                        if matches:
                            # We'll treat freq as "n/a" for each found genotype
                            for m_ in matches:
                                found_pairs.append((m_, "n/a"))

                    unique_geno_pairs = []
                    for gp in found_pairs:
                        if gp not in unique_geno_pairs:
                            unique_geno_pairs.append(gp)

                    # We only keep up to 3
                    # if user wants population freq => we try from AlleleFrequencyFinder:
                    aff = AlleleFrequencyFinder()
                    freq_info = "n/a"
                    if rs_num != "n/a":
                        data = aff.get_allele_frequencies(rs_num)
                        if data:
                            freq_info = aff.build_freq_info_text(data)
                    # We'll store freq_info in each genotype. For simplicity, we store the same freq in each
                    # or parse it?
                    # We'll do the same freq in each genotype for demonstration
                    final_gens = []
                    for i_g, gp in enumerate(unique_geno_pairs[:3]):
                        final_gens.append((gp[0], freq_info))

                    # store in paper_data
                    paper_data["gene"] = gene_name
                    paper_data["rs"] = rs_num
                    paper_data["genotypes"] = final_gens
                    paper_data["date_of_publication"] = date_of_pub
                    paper_data["study_size"] = study_size
                    paper_data["key_findings"] = key_findings_result
                    paper_data["results"] = ergebnisse
                    paper_data["conclusion"] = schlussf

                    fill_paper_in_template(ws, rowOffset, paper_data)
                    rowOffset += 25  # next paper => shift 25 rows downward

                # done
                output_buffer = io.BytesIO()
                wb.save(output_buffer)
                output_buffer.seek(0)

            st.success("Vorlage-Excel wurde gefüllt!")
            st.download_button(
                label="Download Excel (Vorlage-Fix)",
                data=output_buffer,
                file_name="analysis_results_with_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
