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
    """Entfernt alle HTML-Tags außer <br>."""
    return re.sub(r'</?(?!br\b)[^>]*>', '', text)

def translate_text_openai(text, source_language, target_language, api_key):
    """Übersetzt Text über OpenAI-ChatCompletion (z.B. GPT-4)."""
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
        # Entferne mögliche umschließende Anführungszeichen
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
    """Beispiel-Implementierung der CORE-API."""
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
    """Einfacher Verbindungstest zur CORE-API."""
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query, api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"):
    """Einfacher CORE-Search."""
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
    """Testet einfache Verbindung zu PubMed."""
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
    """PubMed-Suche (vereinfacht)."""
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
    """Holt Abstract via efetch für eine gegebene PubMed-ID."""
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

# ... weitere Check-/Search-Funktionen für Europe PMC, OpenAlex usw. könnten hier folgen ...

class PaperAnalyzer:
    """Kernklasse zur PDF-Analyse und GPT-Abfrage."""
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """Extrahiert reinen Text via PyPDF2."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """Hilfsfunktion für ChatCompletion-Aufrufe."""
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
        """Erstellt eine strukturierte Zusammenfassung."""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere sie in mindestens vier klar getrennte Abschnitte "
            "(z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text, api_key):
        """Extrahiert 5 wichtigste Erkenntnisse."""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen "
            "Paper im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text, api_key):
        """Identifiziert Methoden & Techniken."""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text, topic, api_key):
        """Bewertet die Relevanz für ein bestimmtes Thema."""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf "
            f"einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

class AlleleFrequencyFinder:
    """Zum Abrufen der Allelfrequenzen (z.B. via Ensembl REST-API)."""
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
        """Optional: andere Quellen probieren."""
        return None

    def build_freq_info_text(self, data: Dict[str, Any]) -> str:
        """Erzeugt kompakten Infotext über Frequenzen/MAF."""
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

def split_summary(summary_text: str):
    """Versucht, 'Ergebnisse' / 'Schlussfolgerungen' aufzuteilen."""
    m = re.search(r'Ergebnisse\s*:\s*(.*?)\s*Schlussfolgerungen\s*:\s*(.*)', summary_text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    else:
        return summary_text, ""

def parse_cohort_info(summary_text: str) -> dict:
    """
    Sucht z.B. nach '693 Filipino children' usw., um study_size / origin zu bestimmen.
    """
    info = {"study_size": "", "origin": ""}

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

    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )

    compare_mode = st.sidebar.checkbox("Alle Paper gemeinsam vergleichen (Outlier ausschließen)?")

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

    if uploaded_files and api_key:
        # --- Vergleichsmodus ---
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

                if theme_mode == "Manuell":
                    st.write(f"Hauptthema (manuell): {user_defined_theme}")
                    relevant_papers = list(paper_map.keys())
                    st.info("Keine Outlier ausgeschlossen, da 'Manuell' gewählt.")
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
                        return

                    st.markdown("#### GPT-Ausgabe (JSON):")
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
                        return

                    st.write(f"**Hauptthema (GPT)**: {main_theme}")
                    relevant_papers = []
                    st.write("**Paper-Einstufung**:")
                    for p in papers_info:
                        fname = p.get("filename","?")
                        rel = p.get("relevant", False)
                        reason = p.get("reason","(none)")
                        if rel:
                            relevant_papers.append(fname)
                            st.success(f"{fname} => relevant. Begründung: {reason}")
                        else:
                            st.warning(f"{fname} => NICHT relevant. Begründung: {reason}")

                    if not relevant_papers:
                        st.error("Keine relevanten Paper übrig.")
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
            # Einzel-/Multi-Modus
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

                    st.write(f"**Ergebnis für {fpdf.name}:**\n\n{result}")

    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_files:
            st.info("Bitte eine oder mehrere PDF-Dateien hochladen!")

    st.write("---")
    st.write("## Alle Analysen & Excel-Ausgabe (Multi-PDF)")

    # EXISTIERENDE Logik: Multi-Gene in Sheets
    if uploaded_files and api_key:
        user_relevance_score = st.text_input("Manuelle Relevanz-Einschätzung (1-10)?")
        if st.button("Alle Analysen durchführen & in Excel speichern (Multi)"):
            with st.spinner("Analysiere alle hochgeladenen PDFs..."):
                import openpyxl
                import datetime
                try:
                    wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                except FileNotFoundError:
                    st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                    st.stop()

                gen_sheets = {}
                analyzer = PaperAnalyzer(model=model)

                for fpdf in uploaded_files:
                    text = analyzer.extract_text_from_pdf(fpdf)
                    if not text.strip():
                        st.error(f"Kein Text aus {fpdf.name} extrahierbar (evtl. kein OCR). Überspringe...")
                        continue

                    summary_result = analyzer.summarize(text, api_key)
                    key_findings_result = analyzer.extract_key_findings(text, api_key)
                    if not topic:
                        st.error("Bitte 'Thema für Relevanz-Bewertung' angeben!")
                        st.stop()
                    relevance_result = analyzer.evaluate_relevance(text, topic, api_key)
                    methods_result = analyzer.identify_methods(text, api_key)

                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    match_text = re.search(pattern_obvious, text)
                    gene_via_text = match_text.group(1) if match_text else None

                    if not gene_via_text:
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
                        for g in gene_names_from_excel:
                            pat = re.compile(r"\b" + re.escape(g) + r"\b", re.IGNORECASE)
                            if re.search(pat, text):
                                gene_via_text = g
                                break

                    found_gene = gene_via_text
                    rs_pat = r"(rs\d+)"
                    found_rs_match = re.search(rs_pat, text)
                    rs_num = found_rs_match.group(1) if found_rs_match else None

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
                    freq_info = "Keine rsID vorhanden"
                    if rs_num:
                        data = aff.get_allele_frequencies(rs_num)
                        if not data:
                            data = aff.try_alternative_source(rs_num)
                        if data:
                            freq_info = aff.build_freq_info_text(data)

                    sheet_name = found_gene if found_gene else "GEN_UNKNOWN"
                    sheet_name = sheet_name[:27]

                    if sheet_name not in gen_sheets:
                        try:
                            new_sheet = wb.create_sheet(sheet_name)
                            new_sheet["A1"] = "Dateiname"
                            new_sheet["B1"] = "Gene"
                            new_sheet["C1"] = "rsID"
                            new_sheet["D1"] = "Genotype Pairs"
                            new_sheet["E1"] = "Freq Info"
                            new_sheet["F1"] = "Summary"
                            new_sheet["G1"] = "Key Findings"
                            new_sheet["H1"] = "Methods"
                            new_sheet["I1"] = "Relevance"
                            new_sheet["J1"] = "Timestamp"
                            gen_sheets[sheet_name] = new_sheet
                        except:
                            gen_sheets[sheet_name] = wb[sheet_name]
                    else:
                        new_sheet = gen_sheets[sheet_name]

                    next_row = new_sheet.max_row + 1

                    new_sheet.cell(row=next_row, column=1).value = fpdf.name
                    new_sheet.cell(row=next_row, column=2).value = found_gene
                    new_sheet.cell(row=next_row, column=3).value = rs_num
                    all_gps = ",".join([x[0] for x in unique_geno_pairs])
                    new_sheet.cell(row=next_row, column=4).value = all_gps
                    new_sheet.cell(row=next_row, column=5).value = freq_info
                    new_sheet.cell(row=next_row, column=6).value = summary_result
                    new_sheet.cell(row=next_row, column=7).value = key_findings_result
                    new_sheet.cell(row=next_row, column=8).value = methods_result
                    combined_relevance = f"{relevance_result}\n(Manuell:{user_relevance_score})"
                    new_sheet.cell(row=next_row, column=9).value = combined_relevance
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    new_sheet.cell(row=next_row, column=10).value = now_str

            output_buffer = io.BytesIO()
            wb.save(output_buffer)
            output_buffer.seek(0)

            st.success("Alle PDFs verarbeitet – Excel-Datei mit mehreren Sheets erstellt!")
            st.download_button(
                label="Download Excel (Multi-Gene)",
                data=output_buffer,
                file_name="analysis_results_multi.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # NEUE LOGIK: Pro PDF eine eigene Excel-Datei + kombiniertes Workbook
    if uploaded_files and api_key:
        user_relevance_score_2 = st.text_input("Manuelle Relevanz (2) (1-10)?", value="(optional)")
        if st.button("Alle Analysen durchführen & Excel-Dateien erstellen"):
            with st.spinner("Analysiere alle hochgeladenen PDFs..."):
                import openpyxl
                import datetime
                import os
                import shutil
                
                # Temporäres Verzeichnis für die einzelnen Excel-Dateien
                temp_dir = "temp_excel_files"
                os.makedirs(temp_dir, exist_ok=True)
                
                # Liste der erstellten Excel-Dateien
                excel_files = []
                
                analyzer = PaperAnalyzer(model=model)

                # Falls Compare => nur relevante
                if compare_mode:
                    if not st.session_state.get("relevant_papers_compare"):
                        paper_map_auto = {}
                        for fpdf in uploaded_files:
                            txt = analyzer.extract_text_from_pdf(fpdf)
                            if txt.strip():
                                paper_map_auto[fpdf.name] = txt
                        if not paper_map_auto:
                            st.error("Keine verwertbaren Paper.")
                            return
                        relevant_papers_auto, discovered_theme_auto = [], ""
                        # In diesem Beispiel: wir sagen, wir nehmen alle (könnte man GPT-Filter hier anwenden)
                        relevant_papers_auto = list(paper_map_auto.keys())
                        st.session_state["relevant_papers_compare"] = relevant_papers_auto
                        st.session_state["theme_compare"] = discovered_theme_auto

                    relevant_list_for_excel = st.session_state["relevant_papers_compare"] or []
                    if not relevant_list_for_excel:
                        st.error("Keine relevanten Paper nach Outlier-Check für Excel.")
                        return
                    selected_files_for_excel = [f for f in uploaded_files if f.name in relevant_list_for_excel]
                else:
                    selected_files_for_excel = uploaded_files
                
                for i, fpdf in enumerate(selected_files_for_excel):
                    text = analyzer.extract_text_from_pdf(fpdf)
                    if not text.strip():
                        st.error(f"Kein Text aus {fpdf.name} extrahierbar (evtl. kein OCR). Überspringe...")
                        continue
                    
                    # Vorlage für jedes Paper neu laden
                    try:
                        wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                        sheet = wb.active
                    except FileNotFoundError:
                        st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                        return

                    # analyses
                    summary_result = analyzer.summarize(text, api_key)
                    key_findings_result = analyzer.extract_key_findings(text, api_key)
                    if not topic:
                        relevance_result = "(No topic => no Relevanz-Bewertung)"
                    else:
                        relevance_result = analyzer.evaluate_relevance(text, topic, api_key)
                    methods_result = analyzer.identify_methods(text, api_key)

                    # parse gene
                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    match_text = re.search(pattern_obvious, text)
                    gene_via_text = match_text.group(1) if match_text else None

                    if not gene_via_text:
                        try:
                            wb_gene = openpyxl.load_workbook("vorlage_gene.xlsx")
                            ws_gene = wb_gene.active
                            gene_names_from_excel = []
                            for row in ws_gene.iter_rows(min_row=3, min_col=3, max_col=3, values_only=True):
                                cell_value = row[0]
                                if cell_value and isinstance(cell_value, str):
                                    gene_names_from_excel.append(cell_value.strip())
                            for g in gene_names_from_excel:
                                pat = re.compile(r"\b" + re.escape(g) + r"\b", re.IGNORECASE)
                                if re.search(pat, text):
                                    gene_via_text = g
                                    break
                        except FileNotFoundError:
                            st.warning("Die Datei 'vorlage_gene.xlsx' wurde nicht gefunden!")

                    found_gene = gene_via_text
                    rs_pat = r"(rs\d+)"
                    found_rs_match = re.search(rs_pat, text)
                    rs_num = found_rs_match.group(1) if found_rs_match else None

                    genotype_regex = r"\b([ACGT]{2,3})\b"
                    lines = text.split("\n")
                    found_pairs = []
                    for line_ in lines:
                        matches_ = re.findall(genotype_regex, line_)
                        if matches_:
                            for m_ in matches_:
                                found_pairs.append((m_, line_.strip()))

                    unique_geno_pairs = []
                    for gp_ in found_pairs:
                        if gp_ not in unique_geno_pairs:
                            unique_geno_pairs.append(gp_)

                    aff = AlleleFrequencyFinder()
                    freq_info = "Keine rsID vorhanden"
                    if rs_num:
                        data_ = aff.get_allele_frequencies(rs_num)
                        if not data_:
                            data_ = aff.try_alternative_source(rs_num)
                        if data_:
                            freq_info = aff.build_freq_info_text(data_)

                    # In "vorlage_paperqa2.xlsx" bestimmte Zellen befüllen
                    sheet["D5"] = found_gene
                    sheet["D6"] = rs_num

                    for idx_gp, gp_val in enumerate(unique_geno_pairs[:3]):
                        row_geno = 10 + idx_gp
                        sheet[f"D{row_geno}"] = gp_val[0]  # Genotyp
                        sheet[f"E{row_geno}"] = freq_info  # Frequenzinfo

                    # Datum => C20
                    # Studie => D20 => wir nehmen den Dateinamen
                    # KeyFindings => E20
                    # G21 => Ergebnisse, G22 => Schlussfolgerung, H22 => Relevanz
                    now_date = datetime.datetime.now().strftime("%Y-%m-%d")
                    sheet["C20"] = now_date
                    sheet["D20"] = fpdf.name
                    sheet["E20"] = key_findings_result

                    ergebnisse, schlussfolgerungen = split_summary(summary_result)
                    sheet["G21"] = ergebnisse
                    sheet["G22"] = schlussfolgerungen

                    comb_relevance = f"{relevance_result}\n(Manuell:{user_relevance_score_2})"
                    sheet["H22"] = comb_relevance

                    # Speichern
                    safe_filename = re.sub(r'[\\/*?:"<>|]', "_", fpdf.name)
                    excel_path = os.path.join(temp_dir, f"{safe_filename}.xlsx")
                    wb.save(excel_path)
                    excel_files.append(excel_path)

                    st.success(f"Excel-Datei für {fpdf.name} erstellt")

                # Jetzt alle Excel-Dateien zusammenführen
                if excel_files:
                    combined_wb = openpyxl.Workbook()
                    combined_wb.remove(combined_wb.active)  # Standard-Worksheet entfernen

                    for excel_file in excel_files:
                        sheet_name = os.path.basename(excel_file).replace('.xlsx', '')
                        if len(sheet_name) > 31:
                            sheet_name = sheet_name[:31]

                        source_wb = openpyxl.load_workbook(excel_file)
                        source_sheet = source_wb.active

                        target_sheet = combined_wb.create_sheet(title=sheet_name)

                        for row_ in source_sheet.rows:
                            for cell_ in row_:
                                target_sheet[cell_.coordinate].value = cell_.value

                        # Spaltenbreiten kopieren
                        for col_ in source_sheet.columns:
                            letter_ = openpyxl.utils.get_column_letter(col_[0].column)
                            # try:
                            if letter_ in source_sheet.column_dimensions:
                                target_sheet.column_dimensions[letter_].width = source_sheet.column_dimensions[letter_].width

                    combined_buffer = io.BytesIO()
                    combined_wb.save(combined_buffer)
                    combined_buffer.seek(0)

                    st.success("Alle Excel-Dateien wurden erfolgreich kombiniert!")

                    # Download Button - kombinierte Datei
                    st.download_button(
                        label="Download kombinierte Excel-Datei",
                        data=combined_buffer,
                        file_name="combined_analysis_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    # Einzelne Excel-Dateien als ZIP
                    import zipfile
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                        for excel_file in excel_files:
                            zip_file.write(excel_file, os.path.basename(excel_file))

                    zip_buffer.seek(0)
                    st.download_button(
                        label="Download einzelne Excel-Dateien (ZIP)",
                        data=zip_buffer,
                        file_name="individual_analysis_results.zip",
                        mime="application/zip",
                    )

                    # Aufräumen
                    for excel_file in excel_files:
                        try:
                            os.remove(excel_file)
                        except:
                            pass
                    try:
                        os.rmdir(temp_dir)
                    except:
                        pass
                else:
                    st.error("Es wurden keine Excel-Dateien erstellt.")

def sidebar_module_navigation():
    """Einfache Seiten-Navigation."""
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
    """Einfacher Beispiel-Chat."""
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
    # CSS-Anpassungen für das Chat-Fenster
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

        # Automatisches Scrollen
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
