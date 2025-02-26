import os
import sys
import re
import json
import logging
import threading
import time
from datetime import datetime
from io import BytesIO

import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from transformers import pipeline
from scholarly import scholarly
from dotenv import load_dotenv
import openai

# Lade Umgebungsvariablen
load_dotenv()

# API-Schlüssel und Modellnamen
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PHI3_API_KEY = os.getenv("PHI3_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    openai.api_base = "https://api.openai.com/v1"
else:
    logging.warning("OpenAI API-Schlüssel nicht gesetzt.")

# Setze Logging
logging.basicConfig(
    filename='paper_search.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# Hilfsfunktionen
def sanitize_filename(name):
    sanitized = re.sub(r'[\\/*?:\[\]]', '_', name)
    sanitized = sanitized.replace(' ', '_')
    return sanitized[:50]

def extract_text_from_pdf(pdf_bytes):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logging.error(f"Fehler beim Extrahieren aus PDF: {e}")
        return "Textextraktion fehlgeschlagen"

# API-Suchfunktionen (ähnlich wie im Tkinter-Skript)
def search_pubmed(query, retmax=100):
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return []
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        summary_data = r2.json().get("result", {})
        papers = []
        for pmid in idlist:
            info = summary_data.get(pmid, {})
            title = info.get("title", "n/a")
            pubdate = info.get("pubdate", "")
            year = pubdate[:4] if pubdate else "n/a"
            journal = info.get("fulljournalname", "n/a")
            papers.append({
                "source": "PubMed",
                "id": pmid,
                "title": title,
                "journal": journal,
                "link": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmid}/pdf/",
                "abstract": "(Abstract via PubMed nicht geladen)",
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": json.dumps({"PMCID": pmid})
            })
        return papers
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

def search_arxiv(query, max_results=10):
    base_url = "http://export.arxiv.org/api/query"
    params = {"search_query": query, "start": 0, "max_results": max_results}
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        papers = []
        soup = BeautifulSoup(response.content, 'xml')
        entries = soup.find_all('entry')
        for entry in entries:
            paper_id = entry.id.text.strip()
            papers.append({
                "source": "arXiv",
                "id": paper_id,
                "title": entry.title.text.strip(),
                "journal": "arXiv",
                "link": paper_id,
                "abstract": entry.summary.text.strip(),
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": entry.text.strip()
            })
        return papers
    except Exception as e:
        st.error(f"arXiv search error: {e}")
        return []

def search_crossref(query, max_results=10):
    base_url = "https://api.crossref.org/works"
    params = {"query": query, "rows": max_results}
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        papers = []
        for item in data.get('message', {}).get('items', []):
            doi = item.get('DOI', 'N/A')
            title = item.get('title', ['No Title'])[0]
            container_titles = item.get('container-title', ['Unknown'])
            journal = container_titles[0] if container_titles else 'Unknown'
            abstract = item.get('abstract', 'Abstract nicht verfügbar')
            papers.append({
                "source": "CrossRef",
                "id": doi,
                "title": title,
                "journal": journal,
                "link": item.get('URL', ''),
                "abstract": abstract,
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": json.dumps(item, indent=2)
            })
        return papers
    except Exception as e:
        st.error(f"CrossRef search error: {e}")
        return []

def search_semantic_scholar(query, max_results=10):
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"Accept": "application/json"}
    params = {"query": query, "limit": max_results, "fields": "title,authors,journal,abstract,doi,paperId"}
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        papers = []
        for doc in data.get('data', []):
            journal_data = doc.get('journal', 'Unknown')
            if isinstance(journal_data, dict):
                journal = journal_data.get('name', 'Unknown')
            else:
                journal = journal_data
            paper_id = doc.get('externalIds', {}).get('PMID', doc.get('paperId', 'N/A'))
            papers.append({
                "source": "Semantic Scholar",
                "id": paper_id,
                "title": doc.get('title', 'No Title'),
                "journal": journal,
                "link": doc.get('url', ''),
                "abstract": doc.get('abstract', 'Abstract nicht verfügbar'),
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": json.dumps(doc, indent=2)
            })
        return papers
    except Exception as e:
        st.error(f"Semantic Scholar search error: {e}")
        return []

def search_google_scholar(query, max_results=10):
    papers = []
    try:
        results = scholarly.search_pubs(query)
        count = 0
        for result in results:
            if count >= max_results:
                break
            bib = result.get('bib', {})
            title = bib.get('title', 'No Title')
            journal = bib.get('venue', 'Unknown')
            link = result.get('pub_url', '')
            abstract = bib.get('abstract', 'Abstract nicht verfügbar')
            papers.append({
                "source": "Google Scholar",
                "id": "N/A",
                "title": title,
                "journal": journal,
                "link": link,
                "abstract": abstract,
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": str(result)
            })
            count += 1
    except Exception as e:
        st.error(f"Google Scholar search error: {e}")
    return papers

# Beispiel für weitere API-Suchen (CORE Aggregate, Europe PMC, OpenAlex) könnten hier ergänzt werden

# PMCDownloader Klasse für den Download von PMC-Papieren
class PMCDownloader:
    def __init__(self, email, api_key=None):
        self.email = email
        self.api_key = api_key
        self.base_search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        self.base_fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        self.headers = {"User-Agent": f"PMCDownloader/1.0 (mailto:{self.email})"}
        self.api_key_param = f"&api_key={self.api_key}" if self.api_key else ""

    def search_free_pmc_articles(self, query, max_results=10):
        full_query = f"{query} AND free full text[sb]"
        params = {"db": "pmc", "term": full_query, "retmax": max_results, "retmode": "json"}
        try:
            response = requests.get(self.base_search_url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logging.error(f"PMCDownloader Search-Fehler: {e}")
            return []

    def get_paper_info(self, pmcid):
        fetch_params = {"db": "pmc", "id": pmcid, "retmode": "xml", "rettype": "abstract"}
        try:
            response = requests.get(self.base_fetch_url, params=fetch_params, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'xml')
            article = soup.find('article')
            if not article:
                return None
            title_tag = article.find('article-title')
            title = title_tag.get_text(strip=True) if title_tag else 'No Title'
            journal_tag = article.find('journal-title')
            journal = journal_tag.get_text(strip=True) if journal_tag else 'Unknown'
            abstract_tag = article.find('abstract')
            abstract = abstract_tag.get_text(strip=True) if abstract_tag else 'Abstract nicht verfügbar'
            link = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
            esummary = {"PMCID": pmcid}
            return {
                "source": "PubMed",
                "id": pmcid,
                "title": title,
                "journal": journal,
                "link": link,
                "abstract": abstract,
                "impact_factor": 1.0,
                "pdf_text": "Keine PDF verfügbar",
                "esummary": json.dumps(esummary)
            }
        except Exception as e:
            logging.error(f"Fehler beim Abrufen der Papierdetails für PMCID {pmcid}: {e}")
            return None

    def download_pmc_articles(self, pmcids, save_dir):
        os.makedirs(save_dir, exist_ok=True)
        for pmcid in pmcids:
            try:
                url = f"{self.base_fetch_url}?db=pmc&id={pmcid}&retmode=binary&rettype=pdf{self.api_key_param}"
                response = requests.get(url, headers=self.headers, timeout=60)
                response.raise_for_status()
                pdf_path = os.path.join(save_dir, f"{pmcid}.pdf")
                with open(pdf_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logging.info(f"PMC Artikel heruntergeladen: {pmcid}")
            except Exception as e:
                logging.error(f"Fehler beim Download von PMCID {pmcid}: {e}")

# Dummy-Implementierungen für QA-Methoden (Perplexity, Phi3, GPT-4) – ggf. anpassen!
def query_perplexity_ai(question, context):
    if not PERPLEXITY_API_KEY:
        return "Perplexity API-Schlüssel nicht gesetzt."
    # Hier könnte ein echter API-Aufruf erfolgen; wir simulieren eine Antwort.
    return f"Perplexity-Antwort auf: {question}"

def query_phi3_ai(question, context):
    if not PHI3_API_KEY:
        return "Phi3 API-Schlüssel nicht gesetzt."
    return f"Phi3-Antwort auf: {question}"

def query_gpt4_ai(question, context):
    if not OPENAI_API_KEY:
        return "OpenAI API-Schlüssel nicht gesetzt."
    try:
        prompt = f"Hier sind mehrere Paper:\n\n{context}\nBitte beantworte:\nFrage: {question}\nAntwort:"
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        logging.error(f"Fehler bei GPT-4: {e}")
        return f"Fehler bei GPT-4: {e}"

#############################################
# Excel Export Funktion
#############################################
def save_to_excel_with_abstracts_and_esummary(papers, qa_methods_selected):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    main_sheet = wb.active
    main_sheet.title = "Main Results"
    headers = ["Index", "Source", "Title", "ID", "Journal", "Impact Factor", "Link", "Abstract", "PDF Text"] \
              + [f"Antwort ({method})" for method in qa_methods_selected] \
              + ["Download", "Download PDF", "PDF Download Status"]
    main_sheet.append(headers)
    for idx, paper in enumerate(papers, start=1):
        source = paper.get('source', 'Unknown')
        paper_id = paper.get('id', 'N/A')
        title = paper.get('title', 'No Title')
        journal = paper.get('journal', 'Unknown')
        impact_factor = paper.get('impact_factor', 1.0)
        link = paper.get('link', '')
        abstract = paper.get('abstract', 'Abstract nicht verfügbar')
        pdf_text = paper.get('pdf_text', 'PDF Text nicht verfügbar')
        pdf_status = "Erfolgreich" if pdf_text not in ["PDF-Download fehlgeschlagen", "Keine direkte PDF verfügbar"] else pdf_text
        antworten = []
        for method in qa_methods_selected:
            antwort_key = f'antwort_{method.lower()}'
            antworten.append(paper.get(antwort_key, 'Keine Antwort'))
        row = [idx, source, title, paper_id, journal, impact_factor, link, abstract, pdf_text] + antworten + ["Download", "Download PDF", pdf_status]
        main_sheet.append(row)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

#############################################
# Streamlit Haupt-App
#############################################
def main():
    st.title("Paper Search Tool")
    st.markdown("Diese Anwendung sucht wissenschaftliche Paper über verschiedene APIs, führt QA durch und bietet PDF‑Download sowie Excel‑Export.")

    # Sidebar Einstellungen
    st.sidebar.header("Suchparameter")
    search_input = st.sidebar.text_input("Suchbegriffe (durch Komma getrennt)", value="machine learning")
    max_results = st.sidebar.number_input("Max. Ergebnisse pro API", min_value=3, max_value=100, value=10)

    st.sidebar.header("APIs auswählen")
    api_options = {
        "PubMed": True,
        "arXiv": False,
        "CrossRef": False,
        "Semantic Scholar": False,
        "Google Scholar": False
    }
    selected_apis = [api for api, default in api_options.items() if st.sidebar.checkbox(api, value=default)]

    st.sidebar.header("QA-Methoden")
    qa_options = {
        "Transformers (lokales Modell)": True,
        "OpenAI API (ChatGPT)": False,
        "Perplexity AI": False,
        "Deepseek": False,
        "Phi3": False,
        "GPT-4": False
    }
    selected_qa = [method for method, default in qa_options.items() if st.sidebar.checkbox(method, value=default)]

    # Auswahl des Transformer-Modells
    transformer_model = st.sidebar.selectbox("Transformers Modell", [
        "distilbert-base-uncased-distilled-squad",
        "bert-base-uncased",
        "roberta-base",
        "albert-base-v2",
        "bert-large-uncased",
        "bert-base-multilingual-cased",
        "xlm-roberta-base",
        "camembert-base",
        "longformer-base-4096",
        "funnel-transformer/small"
    ])

    # File uploader für QA aus Excel (optional)
    excel_file = st.sidebar.file_uploader("QA aus Excel starten (optional)", type=["xlsx", "xls"])

    # File uploader für lokale Paper (Paperpa)
    pdf_files = st.sidebar.file_uploader("Lokale PDFs hochladen (Paperpa)", type=["pdf"], accept_multiple_files=True)

    # Hauptbereich: Buttons für Aktionen
    if st.button("Suche starten"):
        if not search_input:
            st.error("Bitte Suchbegriffe eingeben!")
        else:
            # Erstelle Suchabfrage
            terms = [term.strip() for term in search_input.split(",") if term.strip()]
            query = " AND ".join(terms)
            st.info(f"Starte Suche mit Abfrage: {query}")
            papers = []

            if "PubMed" in selected_apis:
                papers.extend(search_pubmed(query, max_results))
            if "arXiv" in selected_apis:
                papers.extend(search_arxiv(query, max_results))
            if "CrossRef" in selected_apis:
                papers.extend(search_crossref(query, max_results))
            if "Semantic Scholar" in selected_apis:
                papers.extend(search_semantic_scholar(query, max_results))
            if "Google Scholar" in selected_apis:
                papers.extend(search_google_scholar(query, max_results))

            if not papers:
                st.warning("Keine Ergebnisse gefunden.")
            else:
                st.success(f"{len(papers)} Paper gefunden.")
                df = pd.DataFrame(papers)
                st.dataframe(df[["source", "title", "journal", "link", "abstract"]])
                st.session_state["papers"] = papers
                st.session_state["query"] = query

    # QA: Frage eingeben und Antworten generieren
    st.header("Frage-Antwort-System")
    question = st.text_input("Bitte geben Sie Ihre Frage ein:")
    if st.button("Frage stellen"):
        if "papers" not in st.session_state:
            st.error("Zuerst bitte eine Suche durchführen!")
        elif not question:
            st.error("Bitte eine Frage eingeben!")
        else:
            # Kontext aus allen gefundenen Papern
            context = ""
            for paper in st.session_state["papers"]:
                context += f"Titel: {paper['title']}\nJournal: {paper['journal']}\nAbstract: {paper['abstract']}\n\n"
            responses = {}
            for method in selected_qa:
                try:
                    if "Transformers" in method:
                        qa_pipeline_local = pipeline("question-answering", model=transformer_model)
                        answer = qa_pipeline_local(question=question, context=context)
                        responses[method] = answer['answer']
                    elif "OpenAI" in method:
                        prompt = f"Hier sind mehrere Paper:\n\n{context}\nBitte beantworte:\nFrage: {question}\nAntwort:"
                        response = openai.ChatCompletion.create(
                            model=OPENAI_MODEL,
                            messages=[
                                {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=500,
                            temperature=0.7
                        )
                        responses[method] = response.choices[0].message['content'].strip()
                    elif "Perplexity" in method:
                        responses[method] = query_perplexity_ai(question, context)
                    elif "Deepseek" in method:
                        # Hier könnte ein Aufruf an Deepseek erfolgen
                        responses[method] = "Deepseek Antwort (Platzhalter)"
                    elif "Phi3" in method:
                        responses[method] = query_phi3_ai(question, context)
                    elif "GPT-4" in method:
                        responses[method] = query_gpt4_ai(question, context)
                    else:
                        responses[method] = "Ungültige QA-Methode."
                except Exception as e:
                    responses[method] = f"Fehler: {e}"
                    logging.error(f"Fehler bei QA mit {method}: {e}")
            for method, answer in responses.items():
                st.write(f"**Antwort ({method}):** {answer}")

    # QA aus Excel verarbeiten
    if excel_file:
        try:
            df = pd.read_excel(excel_file)
            st.write("Fragen aus Excel:")
            st.dataframe(df)
            # Dummy-Verarbeitung: Hier könnte man die QA-Funktion für jede Frage aufrufen
            # und die Antworten in der Excel-Datei speichern.
            st.info("QA aus Excel wird noch implementiert...")
        except Exception as e:
            st.error(f"Fehler beim Verarbeiten der Excel-Datei: {e}")

    # Lokale PDFs verarbeiten (Paperpa)
    if pdf_files:
        st.write("Verarbeitete PDFs:")
        local_papers = []
        for uploaded_file in pdf_files:
            pdf_bytes = uploaded_file.read()
            extracted_text = extract_text_from_pdf(pdf_bytes)
            # Dummy-Extraktion des Abstracts
            abstract = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
            paper = {
                "source": "Lokales Paper",
                "id": sanitize_filename(uploaded_file.name),
                "title": uploaded_file.name,
                "journal": "N/A",
                "link": "Lokale Datei",
                "abstract": abstract,
                "impact_factor": 1.0,
                "pdf_text": extracted_text,
                "esummary": "N/A"
            }
            local_papers.append(paper)
        st.session_state["local_papers"] = local_papers
        df_local = pd.DataFrame(local_papers)
        st.dataframe(df_local[["source", "title", "abstract"]])

    # Excel Export der Suchergebnisse
    if "papers" in st.session_state and st.button("Ergebnisse als Excel herunterladen"):
        qa_methods_selected = selected_qa  # Verwende die in der Sidebar ausgewählten QA-Methoden
        excel_bytes = save_to_excel_with_abstracts_and_esummary(st.session_state["papers"], qa_methods_selected)
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sanitized_query = sanitize_filename(st.session_state.get("query", "query"))
        filename = f"search_results_{sanitized_query}_{current_time}.xlsx"
        st.download_button("Excel herunterladen", excel_bytes, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Button zum Training der lokalen Modelle (Train Models)
    if st.button("Train Models"):
        st.info("Starte Trainingsskript...")
        # Hier wird angenommen, dass train_models.py im selben Verzeichnis liegt.
        try:
            subprocess.Popen([sys.executable, 'train_models.py'])
            st.success("Training gestartet.")
        except Exception as e:
            st.error(f"Fehler beim Starten des Trainings: {e}")

    # PaperQA2 Modul aufrufen
    if st.button("PaperQA2 Modul öffnen"):
        st.subheader("PaperQA2 Modul")
        # Hier wird die Funktion module_paperqa2() aufgerufen, die alle PaperQA2‑Funktionen enthält.
        module_paperqa2()

if __name__ == '__main__':
    main()
