import streamlit as st
import requests
import feedparser
import pandas as pd
import os
import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import base64
import sys
import openai

# -------------------------------------------------------------
# Absoluten Pfad zum aktuellen Skript ermitteln
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Versuche zuerst, den Ordner "modules/paper-qa" zu finden.
paperqa_local_path = os.path.join(BASE_DIR, "modules", "paper-qa")
if not os.path.isdir(paperqa_local_path):
    # Falls nicht vorhanden, als Alternative "<BASE_DIR>/paper-qa" verwenden.
    alternative_path = os.path.join(BASE_DIR, "paper-qa")
    if os.path.isdir(alternative_path):
        paperqa_local_path = alternative_path
    else:
        st.error(f"Verzeichnis nicht gefunden: {paperqa_local_path} oder {alternative_path}")
        st.stop()

# Füge den gefundenen Pfad in sys.path ein, damit Python den Unterordner "paperqa" findet.
sys.path.insert(0, paperqa_local_path)

# Versuche, das Modul "paperqa" zu importieren.
try:
    from paperqa import Docs
except ImportError as e:
    st.error(
        "Konnte 'paperqa' nicht importieren.\n"
        "Bitte prüfe, ob im folgenden Ordner 'paperqa/__init__.py' existiert:\n"
        f"{os.path.join(paperqa_local_path, 'paperqa')}"
    )
    st.stop()

# Google Scholar (optional)
try:
    from scholarly import scholarly
except ImportError:
    st.warning("Bitte installiere 'scholarly' via: pip install scholarly")

try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf' via: pip install fpdf")


###############################################################################
# A) ChatGPT: Paper erstellen & lokal speichern
###############################################################################
def generate_paper_via_chatgpt(prompt_text, model="gpt-3.5-turbo"):
    try:
        openai.api_key = st.secrets["OPENAI_API_KEY"]
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei ChatGPT-API: {e}")
        return ""


def save_text_as_pdf(text, pdf_path, title="Paper"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    font_path = os.path.join(BASE_DIR, "modules", "DejaVuSansCondensed.ttf")
    if not os.path.exists(font_path):
        st.error(f"TTF Font file not found: {font_path}")
    else:
        pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", "", 12)
    
    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)
    for line in text.split("\n"):
        pdf.multi_cell(0, 8, line)
        pdf.ln(2)
    pdf.output(pdf_path, "F")


###############################################################################
# B) arXiv-Suche & Download & lokal speichern
###############################################################################
def search_arxiv_papers(query, max_results=5):
    base_url = "http://export.arxiv.org/api/query?"
    params = {"search_query": f"all:{query}", "start": 0, "max_results": max_results}
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Fehler bei arXiv: {e}")
        return []
    
    feed = feedparser.parse(response.text)
    papers_info = []
    for entry in feed.entries:
        link_pdf = None
        for link in entry.links:
            if link.rel == "related" and "pdf" in link.type:
                link_pdf = link.href
                break
            elif link.type == "application/pdf":
                link_pdf = link.href
                break
        papers_info.append({
            "title": entry.title,
            "summary": entry.summary,
            "pdf_url": link_pdf
        })
    return papers_info


def sanitize_filename(fname):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)


def download_arxiv_pdf(pdf_url, local_filepath):
    try:
        r = requests.get(pdf_url, timeout=15)
        r.raise_for_status()
        with open(local_filepath, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        st.error(f"Fehler beim Download PDF: {e}")
        return False


###############################################################################
# C) Multi-API-Suche (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)
###############################################################################
def esearch_pubmed(query: str, max_results=100, timeout=10):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []


def parse_efetch_response(xml_text: str):
    root = ET.fromstring(xml_text)
    pmid_abstract_map = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid_val = pmid_el.text if pmid_el is not None else None
        abstract_el = article.find(".//AbstractText")
        abstract_text = abstract_el.text if abstract_el is not None else "n/a"
        if pmid_val:
            pmid_abstract_map[pmid_val] = abstract_text
    return pmid_abstract_map


def fetch_pubmed_abstracts(pmids, timeout=10):
    if not pmids:
        return {}
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return parse_efetch_response(r.text)
    except Exception as e:
        st.error(f"Fehler bei fetch abstracts: {e}")
        return {}


def get_pubmed_details(pmids: list):
    if not pmids:
        return []
    url_summary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    try:
        r_sum = requests.get(url_summary, params=params_sum, timeout=10)
        r_sum.raise_for_status()
        data_summary = r_sum.json()
    except Exception as e:
        st.error(f"PubMed-ESummary: {e}")
        return []
    abstracts_map = fetch_pubmed_abstracts(pmids)
    results = []
    for pmid in pmids:
        info = data_summary.get("result", {}).get(pmid, {})
        if not info or pmid == "uids":
            continue
        pubdate = info.get("pubdate", "n/a")
        pubyear = pubdate[:4] if len(pubdate) >= 4 else "n/a"
        doi = info.get("elocationid", "n/a")
        title = info.get("title", "n/a")
        abs_text = abstracts_map.get(pmid, "n/a")
        publisher = info.get("fulljournalname") or info.get("source") or "n/a"
        results.append({
            "Source": "PubMed",
            "Title": title,
            "PubMed ID": pmid,
            "Abstract": abs_text,
            "DOI": doi,
            "Year": pubyear,
            "Publisher": publisher,
            "Population": "n/a"
        })
    return results


def search_pubmed(query: str, max_results=100):
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)


def search_europe_pmc(query: str, max_results=100, timeout=10):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": max_results}
    results = []
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        for item in data.get("resultList", {}).get("result", []):
            pub_year = str(item.get("pubYear", "n/a"))
            abstract_text = item.get("abstractText", "n/a")
            jinfo = item.get("journalInfo", {})
            publisher = jinfo.get("journal", "n/a") if isinstance(jinfo, dict) else "n/a"
            results.append({
                "Source": "Europe PMC",
                "Title": item.get("title", "n/a"),
                "PubMed ID": item.get("pmid", "n/a"),
                "Abstract": abstract_text,
                "DOI": item.get("doi", "n/a"),
                "Year": pub_year,
                "Publisher": publisher,
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return results


def search_google_scholar(query: str, max_results=100):
    results = []
    try:
        for idx, pub in enumerate(scholarly.search_pubs(query)):
            if idx >= max_results:
                break
            bib = pub.get("bib", {})
            title = bib.get("title", "n/a")
            year = bib.get("pub_year", "n/a")
            abstract_ = bib.get("abstract", "n/a")
            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": "n/a",
                "Year": str(year),
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Google Scholar-Suche: {e}")
        return []


def search_semantic_scholar(query: str, max_results=100):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": max_results, "fields": "title,authors,year,abstract"}
    results = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        for p in data.get("data", []):
            year_ = str(p.get("year", "n/a"))
            abstract_ = p.get("abstract", "n/a")
            results.append({
                "Source": "Semantic Scholar",
                "Title": p.get("title", "n/a"),
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": "n/a",
                "Year": year_,
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Semantic Scholar: {e}")
        return []


def search_openalex(query: str, max_results=100):
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": max_results}
    results = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        for w in data.get("results", []):
            title = w.get("display_name", "n/a")
            year_ = str(w.get("publication_year", "n/a"))
            doi = w.get("doi", "n/a")
            abstract_ = "n/a"
            results.append({
                "Source": "OpenAlex",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": doi,
                "Year": year_,
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"OpenAlex: {e}")
        return []


###############################################################################
# D) PDF-Helferfunktion: Papers in PDF (Unicode-fähig)
###############################################################################
def create_papers_info_pdf(papers):
    pdf = FPDF()
    pdf.add_page()
    font_path = os.path.join(BASE_DIR, "modules", "DejaVuSansCondensed.ttf")
    if not os.path.exists(font_path):
        st.error(f"Font file not found: {font_path}")
    else:
        pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", "", 12)
    
    pdf.cell(0, 10, "Paper-Informationen (Top 100)", ln=1)
    pdf.ln(5)
    for idx, p in enumerate(papers, start=1):
        title = p.get("Title", "(kein Titel)")
        pmid = p.get("PubMed ID", "n/a")
        doi = p.get("DOI", "n/a")
        pub = p.get("Publisher", "n/a")
        abstr = p.get("Abstract", "n/a")
        pdf.multi_cell(0, 6, f"{idx}) {title}")
        pdf.multi_cell(0, 6, f"   PubMed ID: {pmid}")
        pdf.multi_cell(0, 6, f"   DOI: {doi}")
        pdf.multi_cell(0, 6, f"   Publisher: {pub}")
        pdf.multi_cell(0, 6, f"   Abstract: {abstr}")
        pdf.ln(8)
    return pdf.output(dest="S").encode("latin-1", "replace")


###############################################################################
# E) "Profiles" laden
###############################################################################
def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
    return None


###############################################################################
# G) ChatGPT-Scoring
###############################################################################
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    if not papers:
        return []
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("Kein 'OPENAI_API_KEY' in st.secrets!")
        return []
    progress_area = st.expander("Fortschritt (aktuelles Paper)", expanded=True)
    paper_status = progress_area.empty()
    results_scored = []
    total = len(papers)
    genes_str = ", ".join(genes) if genes else ""
    code_str = codewords if codewords else ""
    for idx, paper in enumerate(papers, start=1):
        paper_title = paper.get("Title", "(kein Titel)")
        paper_status.write(f"Paper {idx}/{total}: **{paper_title}**")
        prompt_text = (
            f"Codewörter: {code_str}\n"
            f"Gene: {genes_str}\n\n"
            f"Paper:\nTitel: {paper_title}\n"
            f"Abstract:\n{paper.get('Abstract','(kein Abstract)')}\n\n"
            "Gib mir eine Zahl von 0 bis 100 (Relevanz)."
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=20,
                temperature=0
            )
            raw_text = response.choices[0].message.content.strip()
            match = re.search(r"(\d+)", raw_text)
            score = int(match.group(1)) if match else 0
        except Exception as e:
            st.error(f"Fehler bei ChatGPT-Scoring: {e}")
            score = 0
        new_p = dict(paper)
        new_p["Relevance"] = score
        results_scored.append(new_p)
    results_scored.sort(key=lambda x: x["Relevance"], reverse=True)
    return results_scored[:top_k]


###############################################################################
# PAPER-QA-ABSCHNITT
###############################################################################
def export_qa_to_excel(qa_history):
    df_qa = pd.DataFrame(qa_history)
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
        df_qa.to_excel(writer, sheet_name="PaperQA_Results", index=False)
    return excel_buf.getvalue()


def paperqa_section(top_results):
    st.write("---")
    st.subheader("Paper-QA (paper-qa) Integration")
    approach = st.radio("Paper-QA Modus:", ["Online mit Abstracts", "Offline mit PDFs"])
    
    if "paperqa_docs" not in st.session_state:
        st.session_state["paperqa_docs"] = None
        st.session_state["paperqa_approach"] = None

    if st.session_state["paperqa_approach"] != approach:
        st.session_state["paperqa_docs"] = None
        st.session_state["paperqa_approach"] = approach

    docs_obj = st.session_state["paperqa_docs"]
    if docs_obj is None:
        if approach == "Online mit Abstracts":
            docs = Docs()
            for i, paper in enumerate(top_results, start=1):
                title = paper.get("Title", "(kein Titel)")
                abstract = paper.get("Abstract", "(kein Abstract)")
                doc_text = f"Paper: {title}\nAbstract:\n{abstract}"
                docs.add(doc_text, f"Paper_{i}")
            st.session_state["paperqa_docs"] = docs
            st.success("Top-100 (Abstracts) in PaperQA geladen (Online).")
        else:
            st.info("Bitte lade PDF-Dateien hoch (Offline-Modus).")
            uploaded_pdfs = st.file_uploader("PDFs hochladen", type=["pdf"], accept_multiple_files=True)
            if uploaded_pdfs:
                docs = Docs()
                for upf in uploaded_pdfs:
                    pdf_bytes = upf.read()
                    try:
                        docs.add(pdf_bytes, metadata=upf.name)
                    except Exception as e:
                        st.error(f"Fehler beim Einlesen von {upf.name}: {e}")
                        return
                st.session_state["paperqa_docs"] = docs
                st.success(f"{len(uploaded_pdfs)} PDF(s) in PaperQA geladen (Offline).")
        docs_obj = st.session_state["paperqa_docs"]

    if docs_obj:
        st.write("---")
        question = st.text_input("Frage an PaperQA:", "")
        if st.button("Frage stellen"):
            try:
                answer = docs_obj.query(question)
                st.write("### Antwort:")
                st.write(answer.answer)
                with st.expander("Kontext"):
                    st.write(answer.context)
                qa_entry = {
                    "Modus": approach,
                    "Frage": question,
                    "Antwort": answer.answer,
                    "Kontext": answer.context[:500],
                    "Zeit": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                if "paperqa_history" not in st.session_state:
                    st.session_state["paperqa_history"] = []
                st.session_state["paperqa_history"].append(qa_entry)
            except Exception as e:
                st.error(f"Fehler bei PaperQA: {e}")
        if st.session_state.get("paperqa_history"):
            st.write("---")
            st.subheader("Q&A-History exportieren")
            excel_data = export_qa_to_excel(st.session_state["paperqa_history"])
            st.download_button(
                label="Download Q&A als Excel",
                data=excel_data,
                file_name="paperqa_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


###############################################################################
# Haupt-Modul: Multi-API-Suche + ChatGPT-Scoring + PaperQA
###############################################################################
def module_codewords_pubmed():
    st.title("Multi-API-Suche + ChatGPT-Scoring + PaperQA (lokales paperqa)")
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte zuerst ein Profil speichern.")
        return

    prof_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + prof_names)

    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = load_settings(chosen_profile)
    if not profile_data:
        st.warning("Profil nicht gefunden oder leer.")
        return

    st.write("Profil-Einstellungen:", profile_data)
    codewords_str = st.text_input("Codewörter:", value=profile_data.get("codewords", ""))
    genes_from_profile = profile_data.get("genes", [])
    st.write(f"Gene: {genes_from_profile}")

    logic_option = st.radio("Logik (AND/OR):", ["OR", "AND"], index=0)

    if st.button("Suche starten"):
        raw_words_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        raw_genes_list = genes_from_profile
        if not raw_words_list and not raw_genes_list:
            st.warning("Keine Codewörter / Gene.")
            return

        if logic_option == "OR":
            q_c = " OR ".join(raw_words_list) if raw_words_list else ""
            q_g = " OR ".join(raw_genes_list) if raw_genes_list else ""
            final_query = f"({q_c}) OR ({q_g})" if q_c and q_g else q_c or q_g
        else:
            q_c = " AND ".join(raw_words_list) if raw_words_list else ""
            q_g = " AND ".join(raw_genes_list) if raw_genes_list else ""
            final_query = f"({q_c}) AND ({q_g})" if q_c and q_g else q_c or q_g

        st.write("**Finale Suchanfrage:**", final_query)

        results_all = []
        active_apis = []
        if profile_data.get("use_pubmed", False):
            pm = search_pubmed(final_query, max_results=200)
            st.write(f"PubMed: {len(pm)}")
            results_all.extend(pm)
            active_apis.append("PubMed")
        if profile_data.get("use_epmc", False):
            ep = search_europe_pmc(final_query, max_results=200)
            st.write(f"Europe PMC: {len(ep)}")
            results_all.extend(ep)
            active_apis.append("Europe PMC")
        if profile_data.get("use_google", False):
            gg = search_google_scholar(final_query, max_results=200)
            st.write(f"Google Scholar: {len(gg)}")
            results_all.extend(gg)
            active_apis.append("Google Scholar")
        if profile_data.get("use_semantic", False):
            se = search_semantic_scholar(final_query, max_results=200)
            st.write(f"Semantic Scholar: {len(se)}")
            results_all.extend(se)
            active_apis.append("Semantic Scholar")
        if profile_data.get("use_openalex", False):
            oa = search_openalex(final_query, max_results=200)
            st.write(f"OpenAlex: {len(oa)}")
            results_all.extend(oa)
            active_apis.append("OpenAlex")

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
            return

        if len(results_all) > 1000:
            results_all = results_all[:1000]

        st.session_state["search_results"] = results_all
        st.session_state["active_apis"] = active_apis
        st.write(f"Gefundene Papers gesamt: {len(results_all)}")
        st.dataframe(pd.DataFrame(results_all))

    if "search_results" in st.session_state and st.session_state["search_results"]:
        st.write("---")
        st.subheader("ChatGPT-Scoring => Top 100")
        all_papers = st.session_state["search_results"]
        if st.button("Starte ChatGPT-Scoring"):
            if not codewords_str.strip() and not genes_from_profile:
                st.warning("Keine Codewörter / Gene -> Abbruch.")
            else:
                top_results = chatgpt_online_search_with_genes(
                    all_papers,
                    codewords=codewords_str,
                    genes=genes_from_profile,
                    top_k=100
                )
                if top_results:
                    st.write("**Top 100 Papers (nach Relevanz)**")
                    df_top = pd.DataFrame({
                        "PubMed ID": [p.get("PubMed ID", "n/a") for p in top_results],
                        "Name": [p.get("Title", "n/a") for p in top_results],
                        "DOI": [p.get("DOI", "n/a") for p in top_results],
                        "Publisher": [p.get("Publisher", "n/a") for p in top_results],
                        "Population": [p.get("Population", "n/a") for p in top_results],
                        "Abstract": [p.get("Abstract", "n/a") for p in top_results],
                        "Relevance": [p.get("Relevance", 0) for p in top_results]
                    })
                    st.dataframe(df_top)

                    active_apis = st.session_state.get("active_apis", [])
                    st.write("---")
                    st.subheader("Sheets pro API")

                    all_papers_df_list = {"Top_100": df_top}
                    for api in active_apis:
                        subset = [p for p in all_papers if p["Source"] == api]
                        df_api = pd.DataFrame(subset)
                        st.markdown(f"**{api}:**")
                        st.dataframe(df_api)
                        all_papers_df_list[api] = df_api

                    st.write("---")
                    st.subheader("Ergebnisse herunterladen")
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                        for sheet_name, df_ in all_papers_df_list.items():
                            safe_sheet = sanitize_filename(sheet_name)[:31] or "API"
                            df_.to_excel(writer, sheet_name=safe_sheet, index=False)
                    excel_data = excel_buffer.getvalue()
                    st.download_button(
                        label="Download als Excel",
                        data=excel_data,
                        file_name="paper_info.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                    pdf_bytes = create_papers_info_pdf(top_results)
                    st.download_button(
                        label="Download als PDF (Top 100)",
                        data=pdf_bytes,
                        file_name="paper_info.pdf",
                        mime="application/pdf"
                    )
                    # PaperQA-Abschnitt:
                    paperqa_section(top_results)


def main():
    st.set_page_config(layout="wide")
    st.title("Kombinierte App: ChatGPT-Paper, arXiv-Suche, Multi-API-Suche + PaperQA (lokales paperqa)")

    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {
            "DefaultProfile": {
                "use_pubmed": True,
                "use_epmc": True,
                "use_google": True,
                "use_semantic": True,
                "use_openalex": True,
                "genes": ["BRCA1", "TP53"],
                "codewords": "cancer therapy"
            }
        }

    menu = ["ChatGPT-Paper", "arXiv-Suche", "Multi-API-Suche"]
    choice = st.sidebar.selectbox("Navigation", menu)
    
    if choice == "ChatGPT-Paper":
        st.subheader("Paper mit ChatGPT generieren & speichern")
        prompt_txt = st.text_area("Prompt:", "Schreibe ein Paper über KI in der Medizin")
        local_dir = st.text_input("Lokaler Ordner:", "chatgpt_papers")
        if st.button("Paper generieren"):
            text = generate_paper_via_chatgpt(prompt_txt)
            if text:
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                pdf_name = f"chatgpt_paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                pdf_path = os.path.join(local_dir, pdf_name)
                save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper")
                st.success(f"Gespeichert: {pdf_path}")

    elif choice == "arXiv-Suche":
        st.subheader("arXiv-Suche + Download PDFs")
        query = st.text_input("Suchbegriff:", "quantum computing")
        num = st.number_input("Max Ergebnisse", 1, 50, 5)
        local_dir_arxiv = st.text_input("Speicherordner:", "arxiv_papers")
        if st.button("arXiv-Suche starten"):
            results = search_arxiv_papers(query, max_results=num)
            if not results:
                st.info("Keine Treffer.")
            else:
                st.write(f"Treffer: {len(results)}")
                if not os.path.exists(local_dir_arxiv):
                    os.makedirs(local_dir_arxiv, exist_ok=True)
                for i, paper in enumerate(results, start=1):
                    st.write(f"**{i})** {paper['title']}")
                    st.write(paper['summary'][:300], "...")
                    if paper["pdf_url"]:
                        fname = sanitize_filename(paper["title"][:50]) + ".pdf"
                        path_ = os.path.join(local_dir_arxiv, fname)
                        if st.button(f"PDF herunterladen: {fname}", key=f"arxiv_{i}"):
                            ok_ = download_arxiv_pdf(paper["pdf_url"], path_)
                            if ok_:
                                st.success(f"PDF gespeichert: {path_}")
                    else:
                        st.write("Kein PDF-Link.")
                    st.write("---")

    else:
        st.subheader("Multi-API-Suche + ChatGPT-Scoring + PaperQA (lokales paperqa)")
        module_codewords_pubmed()


if __name__ == "__main__":
    main()
