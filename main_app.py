#!/usr/bin/env python3

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime
import time
import argparse
import sys
import json
from typing import Dict, Any, Optional

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
# 1) AlleleFrequencyFinder-Klasse (aus deinem Code mit Retries)
################################################################################

class AlleleFrequencyFinder:
    """Klasse zum Abrufen und Anzeigen von Allelfrequenzen aus Ensembl (+ ggf. alternative Quellen)."""
    
    def __init__(self):
        self.ensembl_server = "https://rest.ensembl.org"
        # gnomad_server oder dbSNP-Abfrage könnten hier folgen
        self.max_retries = 3
        self.retry_delay = 2  # Sekunden zwischen Wiederholungsversuchen

    def get_allele_frequencies(self, rs_id: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """
        Ruft Allelfrequenzdaten von Ensembl mit Wiederholungsversuchen ab.
        
        Args:
            rs_id: Die RS-ID (z.B. rs699)
            retry_count: Aktuelle Anzahl der Wiederholungsversuche
            
        Returns:
            Dict mit Allelfrequenzdaten oder None bei Fehlschlag
        """
        if not rs_id.startswith("rs"):
            rs_id = f"rs{rs_id}"
            
        endpoint = f"/variation/human/{rs_id}?pops=1"
        url = f"{self.ensembl_server}{endpoint}"
        
        try:
            response = requests.get(url, headers={"Content-Type": "application/json"}, timeout=10)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            # 500-Fehler => Retry bis max_retries
            if response.status_code == 500 and retry_count < self.max_retries:
                retry_count += 1
                time.sleep(self.retry_delay)
                return self.get_allele_frequencies(rs_id, retry_count)
            elif response.status_code == 404:
                # Variation nicht gefunden
                return None
            else:
                return None
                
        except requests.exceptions.RequestException:
            # Netzwerkausfall etc.
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay)
                return self.get_allele_frequencies(rs_id, retry_count + 1)
            return None

    def try_alternative_source(self, rs_id: str) -> Optional[Dict[str, Any]]:
        """
        Versucht, Daten von einer alternativen Quelle (dbSNP) abzurufen,
        falls Ensembl nicht verfügbar ist.
        """
        # Platzhalter – hier könnte man z.B. dbSNP-Eutilities anfragen
        return None

    def build_freq_info_text(self, data: Dict[str, Any]) -> str:
        """
        Baut einen kurzen Info-Text (ähnlich wie dein parse_and_display_data),
        aber statt console print gibt es einen zusammengefassten String zurück.
        """
        if not data:
            return "Keine Daten verfügbar (None)"

        out_lines = []
        # Variation name
        variant_name = data.get("name", "n/a")
        out_lines.append(f"Variation: {variant_name}")

        # Allele info
        allele_str = None
        if data.get('mappings') and len(data['mappings']) > 0:
            allele_str = data['mappings'][0].get('allele_string')
        if allele_str:
            out_lines.append(f"Allele: {allele_str}")
        
        # MAF
        maf = data.get("MAF", None)
        if maf:
            out_lines.append(f"Globale MAF: {maf}")

        # Populationsfrequenzen
        populations = data.get("populations", [])
        if populations:
            out_lines.append("Populationsfrequenzen (Auszug):")
            # Wir zeigen nur 2 der vorhandenen Populationen
            max_pop = 2
            for i, pop in enumerate(populations[:max_pop]):
                pop_name = pop.get('population', '')
                allele = pop.get('allele', '')
                freq = pop.get('frequency', 0)
                out_lines.append(f"  {pop_name}: {allele}={freq}")
        else:
            out_lines.append("Keine Populationsdaten vorhanden.")

        return " | ".join(out_lines)

################################################################################
# 2) Restliche Komponenten: PubMed, EuropePMC, usw. (unverändert)
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

################################################################################
# 3) Seiten & Module (unverändert)
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
# 4) PAPER ANALYZER
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
# 5) PAGE "Analyze Paper" mit integrierter AlleleFrequencyFinder
################################################################################
def page_analyze_paper():
    """
    Seite "Analyze Paper": ruft direkt den PaperAnalyzer auf.
      * do all 4 GPT analyses
      * liest Gene aus 'vorlage_gene.xlsx' (Spalte C ab Zeile 3)
      * parse for rs... => D6
      * parse for bis zu zwei genotype lines => (D10/F10), (D11/F11)
      * E10/E11 => Frequenzinfo aus AlleleFrequencyFinder() (wenn rs gefunden)
      * J2 = Datum/Zeit
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

    # ALLE ANALYSEN & EXCEL SPEICHERN
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

                # (a) Gene aus 'vorlage_gene.xlsx' auslesen
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
                    pattern = re.compile(r"\b" + re.escape(g) + r"\b", re.IGNORECASE)
                    if re.search(pattern, text):
                        found_gene = g
                        break

                # (b) Excel-Vorlage öffnen
                try:
                    wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
                except FileNotFoundError:
                    st.error("Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                    st.stop()

                ws = wb.active

                if found_gene:
                    ws["D5"] = found_gene

                # (c) SNP-ID (rs\d+)
                rs_pat = r"(rs\d+)"
                found_rs = re.search(rs_pat, text)
                rs_num = None
                if found_rs:
                    rs_num = found_rs.group(1)
                    ws["D6"] = rs_num

                # (d) Genotypen (TT, CC, etc.)
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

                # (e) Frequenz via AlleleFrequencyFinder
                aff = AlleleFrequencyFinder()
                if rs_num:
                    freq_data = aff.get_allele_frequencies(rs_num)
                    if not freq_data:
                        # fallback / alternative
                        freq_data = aff.try_alternative_source(rs_num)
                    # Frequenz-Infos zusammenbauen
                    freq_info_text = aff.build_freq_info_text(freq_data) if freq_data else "Keine Daten von Ensembl/dbSNP"
                else:
                    freq_info_text = "Keine rsID gefunden"

                # (f) Zellen befüllen
                if len(unique_geno_pairs) > 0:
                    ws["D10"] = unique_geno_pairs[0][0]
                    ws["F10"] = unique_geno_pairs[0][1]
                    ws["E10"] = freq_info_text

                if len(unique_geno_pairs) > 1:
                    ws["D11"] = unique_geno_pairs[1][0]
                    ws["F11"] = unique_geno_pairs[1][1]
                    ws["E11"] = freq_info_text

                # Zeitstempel in J2
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ws["J2"] = now_str

                # Speichern
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
# 6) Sidebar Module Navigation & Main
################################################################################

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        # "4) Paper Selection": page_paper_selection,  # auskommentiert
        # "5) Analysis & Evaluation": page_analysis,
        # "6) Extended Topics": page_extended_topics,
        # "7) PaperQA2": module_paperqa2,
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
