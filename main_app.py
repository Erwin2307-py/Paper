import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
import datetime
import os
import PyPDF2
import openai
from dotenv import load_dotenv

# We need openpyxl to read/edit a pre-existing Excel file
import openpyxl
from io import BytesIO

from modules.online_api_filter import module_online_api_filter
from scholarly import scholarly

# -----------------------------------------------------------------------------
# 1) Simple Login
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 2) Basic Streamlit Page Config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# -----------------------------------------------------------------------------
# 3) Some shared search/fetch functions
# -----------------------------------------------------------------------------
def pubmed_fetch_metadata(pmid: str):
    """
    Example function: fetch minimal metadata from PubMed via ESummary.
    Returns a dict with 'title', 'pubdate', 'journal', 'authors', etc. if found.
    """
    if not pmid:
        return {}

    # ESummary call:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        result = data["result"].get(pmid, {})
        return {
            "title": result.get("title", ""),
            "pubdate": result.get("pubdate", ""),
            "journal": result.get("fulljournalname", ""),
            "authors": result.get("authors", []),
        }
    except:
        return {}

# -----------------------------------------------------------------------------
# 4) PaperAnalyzer Class
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 5) Main Page "Analyze Paper"
# -----------------------------------------------------------------------------
def page_analyze_paper():
    """
    This page:
      - Lets user upload a PDF,
      - Optionally supply a PMID to fetch metadata from PubMed,
      - Provide textual fields (e.g., Gen name, rs number, etc.),
      - Perform 4 analyses,
      - Fill them into a pre-existing Excel template (vorlage_paperqa2.xlsx),
      - Then provide a download button.
    """
    st.title("Analyze Paper & Fill Excel Template")

    st.sidebar.header("Einstellungen - PaperAnalyzer")
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    model = st.sidebar.selectbox("OpenAI-Modell",
                                 ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4"],
                                 index=0)
    
    # PDF upload
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")

    # Extra user inputs requested:
    topic = st.text_input("Topic (D2)")
    description = st.text_input("Description (D3)")
    gen_name = st.text_input("Gen Name (D5)")
    rs_number = st.text_input("rs Number (D6)")
    special_comment = st.text_input("Special Comment (D7)")
    genotype = st.text_input("Genotype (D10)")
    population_freq = st.text_input("Population Frequency (E10)")
    phenotype_statements = st.text_area("Phenotype Statements (F10)")
    
    # Possibly from PubMed or from the user
    pmid = st.text_input("PubMed ID (J21). If known, we can fetch metadata.")
    # We can store it to fill J21 with pmid
    fetch_pubmed = st.checkbox("Fetch metadata (date of publication, etc.) from PubMed?")

    # Additional user inputs for the other cells
    # (But if we fetch from PubMed, we might fill them automatically)
    date_of_publication = st.text_input("Date of Publication (C20) - or auto from PubMed if fetch is checked.")
    study_size_ethnicity = st.text_input("Study size & Ethnicity (D20)")
    # We'll fill the 4 analyses in the next step
    # E20 = "summary"
    # G19 = "assessment of paper" (like a short or numeric rating)
    # G21 = "statement about the paper"
    # J21 = pmid
    doi_input = st.text_input("DOI (I22)")
    paper_link = st.text_input("Paper Link (J22)")

    # We will do all 4 analyses with one button:
    analyzer = PaperAnalyzer(model=model)

    if uploaded_file and api_key:
        if st.button("Alle Analysen durchführen & in Excel-Template schreiben"):
            with st.spinner("Lese PDF und führe Analysen durch..."):
                pdf_text = analyzer.extract_text_from_pdf(uploaded_file)
                if not pdf_text.strip():
                    st.error("Kein Text extrahierbar (evtl. gescanntes PDF ohne OCR).")
                    st.stop()

                # Run all 4 analyses
                summary_text = analyzer.summarize(pdf_text, api_key)
                key_findings = analyzer.extract_key_findings(pdf_text, api_key)
                methods_text = analyzer.identify_methods(pdf_text, api_key)

                # Relevance: we use "topic" from user
                if topic.strip():
                    relevance_text = analyzer.evaluate_relevance(pdf_text, topic, api_key)
                else:
                    relevance_text = "(No topic provided, no relevance analysis)"

                # If user wants PubMed fetch
                if pmid and fetch_pubmed:
                    meta = pubmed_fetch_metadata(pmid)
                    # Attempt to parse date from meta["pubdate"]
                    if meta.get("pubdate"):
                        date_of_publication = meta["pubdate"]
                
            # Now open the Excel template with openpyxl
            try:
                wb = openpyxl.load_workbook("vorlage_paperqa2.xlsx")
            except FileNotFoundError:
                st.error("Die Vorlage 'vorlage_paperqa2.xlsx' wurde nicht gefunden!")
                st.stop()

            ws = wb.active  # or use wb["SheetName"] if multiple

            # Fill the cells:
            ws["D2"] = topic
            ws["D3"] = description
            ws["D5"] = gen_name
            ws["D6"] = rs_number
            ws["D7"] = special_comment
            ws["D10"] = genotype
            ws["E10"] = population_freq
            ws["F10"] = phenotype_statements
            # The user specifically asked:
            # - C14: "Summary of Literature Assessments"
            #   We'll store the key_findings + methods together, for example:
            combined_lit_assessment = f"Key Findings:\n{key_findings}\n\nMethods:\n{methods_text}"
            ws["C14"] = combined_lit_assessment

            # C20 = date of publication
            ws["C20"] = date_of_publication
            # D20 = study size & ethnicity
            ws["D20"] = study_size_ethnicity
            # E20 = "summary"
            ws["E20"] = summary_text

            # G19 = "assessment of paper"
            # let's put just a short part of relevance_text. You can parse out if you want a numeric rating
            ws["G19"] = "Assessment: " + relevance_text
            # G21 = "statement about the paper"
            ws["G21"] = "Statement about the paper: " + relevance_text

            # J21 = "pubmed id"
            ws["J21"] = pmid
            # I22 = "doi"
            ws["I22"] = doi_input
            # J22 = "paper link"
            ws["J22"] = paper_link

            # Once done, let's let the user download a copy
            out_buffer = BytesIO()
            wb.save(out_buffer)
            out_buffer.seek(0)

            st.success("Alle Analysen abgeschlossen und Excel-Template gefüllt!")
            st.download_button(
                label="Gefüllte Excel-Datei herunterladen",
                data=out_buffer,
                file_name="filled_paperqa2.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_file:
            st.info("Bitte eine PDF-Datei hochladen!")

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

# -----------------------------------------------------------------------------
# 6) Other pages & Navigation
# -----------------------------------------------------------------------------
def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.image("Bild1.jpg", caption="Willkommen!", use_container_width=False, width=600)

def page_online_api_filter():
    st.title("Online-API_Filter (Kombiniert)")
    st.write("Hier kombinierst du ggf. API-Auswahl und Online-Filter in einem Schritt.")
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,  # our main new page
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
