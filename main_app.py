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
# NEU: Die Klasse AlleleFrequencyFinder (unverändert)
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
# 5) PAGE "Analyze Paper" - Hier wird die Logik für 5) "Grafik & Tabellen Erkennung" eingebunden
################################################################################

def page_analyze_paper():
    """
    Seite "Analyze Paper": ruft direkt den PaperAnalyzer auf.
    * Zuerst versuchen wir, aus dem Text "in the XYZ Gene" zu parsen.
    * Wenn das nicht klappt, fallback: Excel-Liste ...
    * Und neu: 5) Grafiken & Tabellen Erkennung
    """
    import os
    st.title("Analyze Paper - Integriert")

    st.sidebar.header("Einstellungen - PaperAnalyzer")
    # ...

    # 1) BISHERIGE Analyse-Methoden ...
    analysis_mode = st.radio(
        "Wähle die Analyse-Methode aus:",
        [
            "1) Zusammenfassung",
            "2) Wichtigste Erkenntnisse",
            "3) Methoden & Techniken",
            "4) Relevanz-Bewertung",
            "5) Grafiken & Tabellen"
        ]
    )

    if analysis_mode != "5) Grafiken & Tabellen":
        st.info("Die bisherigen Textanalysen ...")
        # ... hier dein bisheriger Code ...
    else:
        # ============== NEUE LOGIK AUS DEINEM SNIPPET ============
        # Skript aus dem Code-Snippet
        st.subheader("Grafik- und Tabellenerkennung in PDF/Bild")

        from PIL import Image
        import numpy as np
        import io
        import base64
        import tempfile
        import os
        import re

        # Bibliotheken für Dokumentenverarbeitung
        from pdf2image import convert_from_bytes
        import pytesseract
        from img2table.ocr import TesseractOCR
        from img2table.document import Image as TableImage

        st.markdown("Lade ein Paper hoch (PDF oder Bild) – wir erkennen Grafiken / Tabellen")

        # OCR-Engine (verwendet Tesseract)
        ocr_engine = st.selectbox("OCR-Engine", ["Tesseract", "EasyOCR"])
        if ocr_engine == "Tesseract":
            lang = st.selectbox("Sprache für OCR", ["eng", "deu", "fra", "ita", "spa", "eng+deu"])
        else:
            lang = "eng"  # fallback

        uploaded_file = st.file_uploader("Paper hochladen (PDF oder Bild)", type=["pdf", "png", "jpg", "jpeg"])

        @st.cache_data
        def convert_pdf_to_images(pdf_bytes):
            return convert_from_bytes(pdf_bytes)

        @st.cache_data
        def extract_tables_from_image(image):
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                image_path = temp.name
                image.save(image_path)

            ocr = TesseractOCR(lang=lang if ocr_engine == "Tesseract" else "eng")
            try:
                table_image = TableImage(image_path)
                tables = table_image.extract_tables(ocr=ocr)
                os.unlink(image_path)
                return [(i, table.df) for i, table in enumerate(tables)]
            except Exception as e:
                st.error(f"Fehler bei der Tabellenextraktion: {e}")
                os.unlink(image_path)
                return []

        @st.cache_data
        def analyze_image_content(image):
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                image_path = temp.name
                image.save(image_path)

            text = pytesseract.image_to_string(image_path, lang=lang if ocr_engine == "Tesseract" else "eng")
            os.unlink(image_path)
            text_lower = text.lower()
            if re.search(r'fig(ure|\.)?|abbildung', text_lower):
                return "Grafik", text
            elif re.search(r'tab(le|\.)|tabelle', text_lower):
                return "Tabelle", text
            elif len(text.strip()) < 50:
                return "Möglicherweise Grafik", text
            else:
                return "Text/Unbestimmt", text

        def get_table_download_link(df, filename="tabelle.csv", text="CSV herunterladen"):
            csv = df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
            return href

        if uploaded_file is not None:
            file_extension = uploaded_file.name.split('.')[-1].lower()
            if file_extension == 'pdf':
                with st.spinner("PDF wird verarbeitet..."):
                    images = convert_pdf_to_images(uploaded_file.getvalue())
                    if images:
                        st.success(f"{len(images)} Seiten erfolgreich extrahiert!")
                        if len(images) > 1:
                            selected_page = st.selectbox("Seite auswählen:", range(1, len(images) + 1)) - 1
                            selected_image = images[selected_page]
                        else:
                            selected_image = images[0]
                        st.image(selected_image, caption=f"Seite {selected_page + 1}", use_column_width=True)

                        analysis_type = st.radio("Analyse durchführen:",
                            ["Tabellenerkennung", "Bildanalyse", "Texterkennung"])

                        if analysis_type == "Tabellenerkennung":
                            if st.button("Tabellen erkennen"):
                                with st.spinner("Tabellen werden erkannt..."):
                                    tables = extract_tables_from_image(selected_image)
                                    if tables:
                                        st.success(f"{len(tables)} Tabellen gefunden!")
                                        for i, df in tables:
                                            st.subheader(f"Tabelle {i+1}")
                                            st.dataframe(df)
                                            st.markdown(get_table_download_link(df, f"tabelle_{i+1}.csv"),
                                                        unsafe_allow_html=True)
                                    else:
                                        st.warning("Keine Tabellen gefunden oder Fehler bei der Erkennung.")

                        elif analysis_type == "Bildanalyse":
                            if st.button("Bildinhalt analysieren"):
                                with st.spinner("Analyse läuft..."):
                                    content_type, extracted_text = analyze_image_content(selected_image)
                                    st.subheader("Analyse-Ergebnis")
                                    st.info(f"Erkannter Inhaltstyp: {content_type}")
                                    if extracted_text:
                                        st.subheader("Extrahierter Text")
                                        st.text_area("", extracted_text, height=200)

                        elif analysis_type == "Texterkennung":
                            if st.button("Text extrahieren"):
                                with st.spinner("Text wird extrahiert..."):
                                    text = pytesseract.image_to_string(selected_image, lang=lang if ocr_engine == "Tesseract" else "eng")
                                    st.subheader("Extrahierter Text")
                                    st.text_area("", text, height=300)

            elif file_extension in ['png', 'jpg', 'jpeg']:
                with st.spinner("Bild wird verarbeitet..."):
                    image = Image.open(uploaded_file)
                    st.image(image, caption="Hochgeladenes Bild", use_column_width=True)
                    analysis_type = st.radio("Analyse durchführen:",
                                    ["Tabellenerkennung", "Bildanalyse", "Texterkennung"])
                    
                    if analysis_type == "Tabellenerkennung":
                        if st.button("Tabellen erkennen"):
                            with st.spinner("Tabellen werden erkannt..."):
                                tables = extract_tables_from_image(image)
                                if tables:
                                    st.success(f"{len(tables)} Tabellen gefunden!")
                                    for i, df in tables:
                                        st.subheader(f"Tabelle {i+1}")
                                        st.dataframe(df)
                                        st.markdown(get_table_download_link(df, f"tabelle_{i+1}.csv"),
                                                    unsafe_allow_html=True)
                                else:
                                    st.warning("Keine Tabellen gefunden oder Fehler bei der Erkennung.")

                    elif analysis_type == "Bildanalyse":
                        if st.button("Bildinhalt analysieren"):
                            with st.spinner("Analyse läuft..."):
                                content_type, extracted_text = analyze_image_content(image)
                                st.subheader("Analyse-Ergebnis")
                                st.info(f"Erkannter Inhaltstyp: {content_type}")
                                if extracted_text:
                                    st.subheader("Extrahierter Text")
                                    st.text_area("", extracted_text, height=200)

                    elif analysis_type == "Texterkennung":
                        if st.button("Text extrahieren"):
                            with st.spinner("Text wird extrahiert..."):
                                text = pytesseract.image_to_string(image, lang=lang if ocr_engine == "Tesseract" else "eng")
                                st.subheader("Extrahierter Text")
                                st.text_area("", text, height=300)
            else:
                st.error("Nicht unterstütztes Dateiformat! Bitte laden Sie eine PDF- oder Bilddatei hoch.")
        else:
            st.info("Bitte laden Sie eine PDF- oder Bilddatei hoch, um die Analyse zu starten.")


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
        "Analyze Paper": page_analyze_paper,
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
