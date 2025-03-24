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

# For translation if needed
from google_trans_new import google_translator

# ------------------------------------------------------------------
# Load environment variables (for OPENAI_API_KEY, if present)
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------------------
# Streamlit configuration
# ------------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# ------------------------------------------------------------------
# Login functionality
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
# 1) Common functions & classes
# ------------------------------------------------------------------

def clean_html_except_br(text):
    """Remove all HTML tags except <br>."""
    return re.sub(r'</?(?!br\b)[^>]*>', '', text)

def translate_text_openai(text, source_language, target_language, api_key):
    """Uses OpenAI ChatCompletion to translate text."""
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
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0
        )
        translation = response.choices[0].message.content.strip()
        # strip quotes if present
        if translation and translation[0] in ["'", '"', "‘", "„"]:
            translation = translation[1:]
            if translation and translation[-1] in ["'", '"']:
                translation = translation[:-1]
        translation = clean_html_except_br(translation)
        return translation
    except Exception as e:
        st.warning(f"Translation Error: {e}")
        return text

# (CORE aggregator search, PubMed search, Europe PMC search, OpenAlex, Google Scholar, Semantic Scholar not shown again for brevity)

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.image("Bild1.jpg", caption="Welcome!", use_container_width=False, width=600)

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_online_api_filter():
    st.title("Online-API_Filter (Combined)")
    st.write("Here you can combine API selection and online filter in one step.")
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

class PaperAnalyzer:
    """A class that extracts text from PDFs and sends it to OpenAI for analysis."""
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """Extract plain text via PyPDF2 (if the PDF is searchable)."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """Generic helper to call OpenAI with a given prompt template."""
        import openai
        openai.api_key = api_key
        if len(text) > 15000:
            text = text[:15000] + "..."
        prompt = prompt_template.format(text=text)
        response = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": (
                    "You are an expert in analyzing scientific papers, especially Side-Channel Analysis."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def summarize(self, text, api_key):
        """Generate a structured summary in German, up to 500 words."""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere sie in mindestens vier klar getrennte Abschnitte "
            "(z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text, api_key):
        """Extract the 5 most important findings (German)."""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper "
            "im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text, api_key):
        """Identify the methods and techniques (German)."""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text, topic, api_key):
        """Evaluate relevance on a scale of 1-10 (German)."""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf "
            f"einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

class AlleleFrequencyFinder:
    """A class to retrieve and display allele frequencies from Ensembl or other sources."""
    def __init__(self):
        self.ensembl_server = "https://rest.ensembl.org"
        self.max_retries = 3
        self.retry_delay = 2

    def get_allele_frequencies(self, rs_id: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """Retrieve allele frequencies from Ensembl."""
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
        """Placeholder if Ensembl fails."""
        return None

    def build_freq_info_text(self, data: Dict[str, Any]) -> str:
        """Generate a short text about allele frequencies."""
        if not data:
            return "No Ensembl Data"
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
            out.append("No population data found.")
        return " | ".join(out)

def split_summary(summary_text):
    """
    Attempt to split 'Ergebnisse' and 'Schlussfolgerungen' from a German summary.
    If not found, fallback is the entire text as 'Ergebnisse', and empty 'Schlussfolgerungen'.
    """
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
    Attempt to parse e.g. # of patients, # of controls, or nationality, from a German summary text.
    Returns a dict with "study_size" and "origin".
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
        info["study_size"] = f"{p_count} patients / {c_count} controls"
    else:
        pattern_single_p = re.compile(r"(\d+)\s*Patient(?:en)?", re.IGNORECASE)
        m_single_p = pattern_single_p.search(summary_text)
        if m_single_p and not info["study_size"]:
            info["study_size"] = f"{m_single_p.group(1)} patients"

    pattern_origin = re.compile(r"in\s*der\s+(\S+)\s+Bevölkerung", re.IGNORECASE)
    m_orig = pattern_origin.search(summary_text)
    if m_orig and not info["origin"]:
        info["origin"] = m_orig.group(1).strip()

    return info

def parse_publication_date(text: str) -> str:
    """
    Looks for 'Published: 20 November 2024' -> returns '20.11.2024'.
    Otherwise returns 'n/a'.
    """
    pattern = re.compile(r"Published:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        day = match.group(1)
        month_str = match.group(2)
        year = match.group(3)

        months_map = {
            "January": "01", "February": "02", "March": "03", "April": "04",
            "May": "05", "June": "06", "July": "07", "August": "08",
            "September": "09", "October": "10", "November": "11", "December": "12"
        }
        month_num = months_map.get(month_str.capitalize(), "01")
        day = day.zfill(2)
        return f"{day}.{month_num}.{year}"
    else:
        return "n/a"

def page_analyze_paper():
    """
    Main page for analyzing papers (uploading PDFs, analyzing them individually,
    or combining them, optionally saving to Excel).
    The 'vorlage_paperqa2.xlsx' MUST remain exactly as it is. We do not alter it.
    If no gene is found in the PDF, we fallback to check 'vorlage_gene.xlsx' to see if any listed gene is present in the text.
    """
    st.title("Analyze Paper - Integrated")

    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""

    st.sidebar.header("Settings - PaperAnalyzer")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value

    model = st.sidebar.selectbox(
        "OpenAI Model",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )

    compare_mode = st.sidebar.checkbox("Compare mode (exclude outlier papers)?")
    theme_mode = st.sidebar.radio("Determine Main Theme", ["Manuell", "GPT"])
    action = st.sidebar.radio(
        "Analysis Type",
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
        user_defined_theme = st.sidebar.text_input("Manual Main Theme (for compare mode)")

    topic = st.sidebar.text_input("Topic (for relevance)?")
    combine_texts_single_analysis = st.sidebar.checkbox("Combine selected PDFs into one single text?")

    uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]

    # Single or combined analysis (no Excel)
    if uploaded_files and api_key:
        st.write("## Single/Multiple Analysis (No Excel)")

        if combine_texts_single_analysis:
            # Combined mode
            if st.button("Start Combined Analysis (No Excel)"):
                combined_text = ""
                for fpdf in uploaded_files:
                    text_data = analyzer.extract_text_from_pdf(fpdf)
                    if not text_data.strip():
                        st.warning(f"No text from {fpdf.name} (skipped).")
                        continue
                    combined_text += f"\n=== {fpdf.name} ===\n{text_data}\n"

                if not combined_text.strip():
                    st.error("No text to analyze from selected PDFs!")
                    return

                result = ""
                if action == "Zusammenfassung":
                    r_ = analyzer.summarize(combined_text, api_key)
                    result = translate_text_openai(r_, "German", "English", api_key)

                elif action == "Wichtigste Erkenntnisse":
                    r_ = analyzer.extract_key_findings(combined_text, api_key)
                    result = translate_text_openai(r_, "German", "English", api_key)

                elif action == "Methoden & Techniken":
                    r_ = analyzer.identify_methods(combined_text, api_key)
                    result = translate_text_openai(r_, "German", "English", api_key)

                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Please provide a topic for relevance!")
                        return
                    r_ = analyzer.evaluate_relevance(combined_text, topic, api_key)
                    result = translate_text_openai(r_, "German", "English", api_key)

                elif action == "Tabellen & Grafiken":
                    st.warning("Tables & Graphics in combined mode are not fully implemented.")
                    result = "(No full table analysis in combined mode)"

                st.subheader("Combined Analysis Result:")
                st.markdown(result)

        else:
            # Normal single or all approach
            pdf_options = ["(All)"] + [f"{i+1}) {f.name}" for i, f in enumerate(uploaded_files)]
            selected_pdf = st.selectbox("Choose a PDF for single analysis or '(All)'", pdf_options)

            if st.button("Start Analysis (No Excel)"):
                if selected_pdf == "(All)":
                    files_to_process = uploaded_files
                else:
                    idx = pdf_options.index(selected_pdf) - 1
                    files_to_process = [uploaded_files[idx]]

                final_result_text = []
                for fpdf in files_to_process:
                    text_data = analyzer.extract_text_from_pdf(fpdf)
                    if not text_data.strip():
                        st.error(f"No text extracted from {fpdf.name}. Skipped.")
                        continue

                    result = ""
                    if action == "Zusammenfassung":
                        r_ = analyzer.summarize(text_data, api_key)
                        result = translate_text_openai(r_, "German", "English", api_key)

                    elif action == "Wichtigste Erkenntnisse":
                        r_ = analyzer.extract_key_findings(text_data, api_key)
                        result = translate_text_openai(r_, "German", "English", api_key)

                    elif action == "Methoden & Techniken":
                        r_ = analyzer.identify_methods(text_data, api_key)
                        result = translate_text_openai(r_, "German", "English", api_key)

                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Please provide a topic for relevance!")
                            continue
                        r_ = analyzer.evaluate_relevance(text_data, topic, api_key)
                        result = translate_text_openai(r_, "German", "English", api_key)

                    elif action == "Tabellen & Grafiken":
                        all_tables_text = []
                        try:
                            with pdfplumber.open(fpdf) as pdf_:
                                for page_number, page in enumerate(pdf_.pages, start=1):
                                    tables = page.extract_tables()
                                    if tables:
                                        for table_idx, table_data in enumerate(tables, start=1):
                                            if not table_data:
                                                continue
                                            first_row = table_data[0]
                                            data_rows = table_data[1:]
                                            if not data_rows:
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
                                                df = pd.DataFrame(table_data)
                                            else:
                                                df = pd.DataFrame(data_rows, columns=new_header)

                                            table_str = df.to_csv(index=False)
                                            all_tables_text.append(
                                                f"Page {page_number}, Table {table_idx}:\n{table_str}\n"
                                            )
                            if len(all_tables_text) > 0:
                                combined_tables = "\n".join(all_tables_text)
                                gpt_prompt = (
                                    "Please analyze the following tables from a scientific PDF. "
                                    "Summarize the key insights and provide a brief interpretation:\n\n"
                                    f"{combined_tables}"
                                )
                                openai.api_key = api_key
                                try:
                                    resp = openai.chat.completions.create(
                                        model=model,
                                        messages=[
                                            {"role": "system", "content": "You are an expert in PDF table analysis."},
                                            {"role": "user", "content": gpt_prompt}
                                        ],
                                        temperature=0.3,
                                        max_tokens=1000
                                    )
                                    result = resp.choices[0].message.content
                                except Exception as e_:
                                    st.error(f"GPT table analysis error: {e_}")
                                    result = "(Error in GPT evaluation for tables)"
                            else:
                                result = "No tables found in the PDF."
                        except Exception as e_:
                            st.error(f"Error reading PDF tables from {fpdf.name}: {e_}")
                            result = f"(Error reading tables in {fpdf.name})"

                    final_result_text.append(f"**Result for {fpdf.name}:**\n\n{result}")

                st.subheader("Analysis Results (No Excel)")
                combined_output = "\n\n---\n\n".join(final_result_text)
                st.markdown(combined_output)

    else:
        if not api_key:
            st.warning("Please enter an OpenAI API key!")
        elif not uploaded_files:
            st.info("Please upload one or more PDF files!")

    # ---------------- Multi-PDF => Excel approach ----------------
    st.write("---")
    st.write("## All Analyses & Excel Output (Multi-PDF)")
    user_relevance_score = st.text_input("Manual Relevance Score (1-10)?")

    if "analysis_results" not in st.session_state:
        st.session_state["analysis_results"] = []

    if uploaded_files and api_key:
        if st.button("Analyze All & Save to Excel (Multi)"):
            st.session_state["analysis_results"] = []
            with st.spinner("Analyzing PDFs..."):
                import openpyxl
                import datetime

                if compare_mode:
                    selected_files_for_excel = uploaded_files
                else:
                    selected_files_for_excel = uploaded_files

                analyzer = PaperAnalyzer(model=model)
                main_theme_final = user_defined_theme.strip() if theme_mode == "Manuell" else "n/a"

                for fpdf in selected_files_for_excel:
                    text_data = analyzer.extract_text_from_pdf(fpdf)
                    if not text_data.strip():
                        st.error(f"No text from {fpdf.name} (skipped).")
                        continue

                    summary_de = analyzer.summarize(text_data, api_key)
                    summary_en = translate_text_openai(summary_de, "German", "English", api_key)
                    keyf_de = analyzer.extract_key_findings(text_data, api_key)
                    keyf_en = translate_text_openai(keyf_de, "German", "English", api_key)

                    ergebnisse_de, schlussfolgerung_de = split_summary(summary_de)
                    ergebnisse_en = translate_text_openai(ergebnisse_de, "German", "English", api_key)
                    schluss_en = translate_text_openai(schlussfolgerung_de, "German", "English", api_key)

                    c_info = parse_cohort_info(summary_de)
                    combined_study = (c_info["study_size"] + " " + c_info["origin"]).strip()
                    if not combined_study:
                        combined_study = "n/a"
                    combined_study_en = translate_text_openai(combined_study, "German", "English", api_key)

                    pub_date_str = parse_publication_date(text_data)

                    # Attempt to parse gene from text
                    pattern_obvious = re.compile(r"in the\s+([A-Za-z0-9_-]+)\s+gene", re.IGNORECASE)
                    match_text = re.search(pattern_obvious, text_data)
                    found_gene = match_text.group(1) if match_text else None

                    # If we didn't find any gene, we check "vorlage_gene.xlsx"
                    if not found_gene:
                        # open 'vorlage_gene.xlsx' and see if any listed gene is in the text
                        try:
                            import openpyxl
                            wb_gene = openpyxl.load_workbook("vorlage_gene.xlsx")
                            ws_gene = wb_gene.active
                            gene_names_from_excel = []
                            # Suppose the gene list is in column C, from row 3 onward
                            for row in ws_gene.iter_rows(min_row=3, min_col=3, max_col=3, values_only=True):
                                cell_value = row[0]
                                if cell_value and isinstance(cell_value, str):
                                    gene_names_from_excel.append(cell_value.strip())
                            for g_candidate in gene_names_from_excel:
                                pat_candidate = re.compile(r"\b" + re.escape(g_candidate) + r"\b", re.IGNORECASE)
                                if re.search(pat_candidate, text_data):
                                    found_gene = g_candidate
                                    break
                        except FileNotFoundError:
                            st.error("File 'vorlage_gene.xlsx' not found! Fallback not possible.")
                            # we keep found_gene as None if not found

                    rs_pat = r"(rs\d+)"
                    match_rs = re.search(rs_pat, text_data)
                    found_rs = match_rs.group(1) if match_rs else None

                    genotype_regex = r"\b([ACGT]{2,3})\b"
                    lines = text_data.split("\n")
                    found_pairs = []
                    for line in lines:
                        matches = re.findall(genotype_regex, line)
                        if matches:
                            for m in matches:
                                found_pairs.append(m)

                    unique_genos = []
                    for g_ in found_pairs:
                        if g_ not in unique_genos:
                            unique_genos.append(g_)
                    genotypes = unique_genos[:3]

                    # freq
                    aff = AlleleFrequencyFinder()
                    freq_info = "No rsID found"
                    if found_rs:
                        data_ = aff.get_allele_frequencies(found_rs)
                        if data_:
                            freq_info = aff.build_freq_info_text(data_)

                    try:
                        from openpyxl import load_workbook
                        wb = load_workbook("vorlage_paperqa2.xlsx")  # EXACT template, no changes
                    except FileNotFoundError:
                        st.error("Template 'vorlage_paperqa2.xlsx' not found!")
                        return

                    ws = wb.active
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
                    ws["J2"] = now_str
                    ws["D2"] = main_theme_final
                    ws["D5"] = found_gene if found_gene else "n/a"
                    ws["D6"] = found_rs if found_rs else "n/a"

                    genotype_cells = ["D10", "D11", "D12"]
                    freq_cells = ["E10", "E11", "E12"]
                    # fill genotype / freq
                    for i in range(3):
                        if i < len(genotypes):
                            ws[genotype_cells[i]] = genotypes[i]
                            ws[freq_cells[i]] = freq_info  # We keep it as 'freq_info' or partial info
                        else:
                            ws[genotype_cells[i]] = ""
                            ws[freq_cells[i]] = ""

                    ws["C20"] = pub_date_str
                    ws["D20"] = combined_study_en
                    ws["E20"] = keyf_en
                    ws["G21"] = ergebnisse_en
                    ws["G22"] = schluss_en

                    output_buffer = io.BytesIO()
                    wb.save(output_buffer)
                    output_buffer.seek(0)

                    st.session_state["analysis_results"].append((fpdf.name, output_buffer))

    # Show the individual Excel download buttons
    if "analysis_results" in st.session_state and st.session_state["analysis_results"]:
        st.write("## Download Analyzed Excel Files (Individual)")
        for (filename, io_obj) in st.session_state["analysis_results"]:
            st.download_button(
                label=f"Download Excel for {filename}",
                data=io_obj.getvalue(),
                file_name=f"analysis_{filename.replace('.pdf', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_{filename}"
            )

        # Additional option to combine all these individual XLSX files into one combined workbook
        st.write("---")
        st.write("## Combine Individual Excel Files into One Workbook (Using EXACT Template Format)")

        if st.button("Combine All Individual XLSX into One Workbook"):
            from openpyxl import load_workbook, Workbook

            combined_wb = Workbook()
            default_sheet = combined_wb.active
            combined_wb.remove(default_sheet)

            # Helper to sanitize sheet name
            def make_safe_sheetname(name: str, maxlen: int = 31) -> str:
                invalid_chars = [":", "*", "/", "\\", "?", "[", "]"]
                for ch in invalid_chars:
                    name = name.replace(ch, "")
                safe_name = name[:maxlen]
                if not safe_name.strip():
                    safe_name = "Sheet"
                return safe_name

            for (filename, io_obj) in st.session_state["analysis_results"]:
                xls_bytes = io_obj.getvalue()
                temp_wb = load_workbook(io.BytesIO(xls_bytes))
                sheet = temp_wb.active

                gene_name = sheet["D5"].value or "GENE_UNKNOWN"
                sheet_name = make_safe_sheetname(gene_name)

                new_ws = combined_wb.create_sheet(sheet_name)
                for row_idx, row_data in enumerate(sheet.iter_rows(values_only=True), start=1):
                    for col_idx, cell_val in enumerate(row_data, start=1):
                        new_ws.cell(row=row_idx, column=col_idx, value=cell_val)

            final_buffer = io.BytesIO()
            combined_wb.save(final_buffer)
            final_buffer.seek(0)

            st.download_button(
                label="Download Combined Workbook",
                data=final_buffer,
                file_name="combined_workbook.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def sidebar_module_navigation():
    """Simple sidebar navigation."""
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
    Simple chat example with possible paper_text context.
    We do not rely on the 'vorlage_paperqa2.xlsx' for this chat example.
    """
    api_key = st.session_state.get("api_key", "")
    paper_text = st.session_state.get("paper_text", "")
    if not api_key:
        return f"(No API-Key) Echo: {question}"

    if not paper_text.strip():
        sys_msg = "You are a helpful assistant for general questions."
    else:
        sys_msg = (
            "You are a helpful assistant, and here is a paper as context:\n\n"
            + paper_text[:12000] + "\n\n"
            "Use it to provide an expert answer."
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
        return f"OpenAI error: {e}"

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

        user_input = st.text_input("Your question here", key="chatbot_right_input")
        if st.button("Send (Chat)", key="chatbot_right_send"):
            if user_input.strip():
                st.session_state["chat_history"].append(("user", user_input))
                bot_answer = answer_chat(user_input)
                st.session_state["chat_history"].append(("bot", bot_answer))

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

        # Auto-scroll script
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
