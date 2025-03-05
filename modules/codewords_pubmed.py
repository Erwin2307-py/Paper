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

# Google Scholar-Scraping:
try:
    from scholarly import scholarly
except ImportError:
    st.error("Bitte installiere 'scholarly' (z.B. pip install scholarly).")

# OpenAI / ChatGPT:
import openai
# Falls du direkt einen Key setzen willst:
# openai.api_key = "sk-XXXX"

# PDF-Erzeugung
try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf' (z.B. pip install fpdf).")

##############################################################################
# Hilfsfunktionen: Flatten Dict, local PDF-Bau etc.
##############################################################################

def flatten_dict(d, parent_key="", sep="__"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def _sanitize_filename(fname):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)

def create_abstract_pdf(paper, output_stream):
    """
    Baut ein PDF mit fpdf; schreibt es als Bytes in output_stream.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    def wrap_text(t, max_len=100):
        chunks = []
        words = t.split()
        for w in words:
            while len(w) > max_len:
                chunks.append(w[:max_len])
                w = w[max_len:]
            chunks.append(w)
        return " ".join(chunks)

    page_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.cell(0, 10, f"Paper: {paper.get('Title','n/a')}", ln=1)
    pdf.ln(2)
    pdf.multi_cell(page_width, 8, wrap_text(f"** Abstract **\n\n{paper.get('Abstract','n/a')}"))
    pdf.ln(2)
    pdf.multi_cell(page_width, 8, wrap_text(f"** Source: {paper.get('Source','n/a')}"))
    pdf.multi_cell(page_width, 8, wrap_text(f"** PubMed ID: {paper.get('PubMed ID','n/a')}"))
    pdf.multi_cell(page_width, 8, wrap_text(f"** DOI: {paper.get('DOI','n/a')}"))
    pdf.multi_cell(page_width, 8, wrap_text(f"** Year: {paper.get('Year','n/a')}"))
    pdf.multi_cell(page_width, 8, wrap_text(f"** Publisher: {paper.get('Publisher','n/a')}"))

    pdf_string = pdf.output(dest='S')  # => str in fpdf 1.x
    pdf_bytes = pdf_string.encode('latin-1', 'replace')
    output_stream.write(pdf_bytes)

def create_gpt_paper_pdf(gpt_text, output_stream, title="ChatGPT Summary"):
    """
    Erzeugt ein PDF aus dem von ChatGPT zurückgelieferten Text.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)

    lines = gpt_text.split("\n")
    for line in lines:
        pdf.multi_cell(0, 8, line)
        pdf.ln(2)

    pdf_str = pdf.output(dest='S')
    pdf_bytes = pdf_str.encode("latin-1", "replace")
    output_stream.write(pdf_bytes)

##############################################################################
# OpenAI-Chat
##############################################################################

def generate_chatgpt_paper(prompt_text):
    """
    Ruft ChatGPT auf, um eine "Paper"-Zusammenfassung zu erzeugen.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1200,
            temperature=0.7
        )
        content = response.choices[0].message.content
        return content
    except Exception as e:
        st.error(f"Fehler bei ChatGPT API: {e}")
        return ""

##############################################################################
# Multi-API-Suchfunktionen (PubMed, Europe PMC, Google Scholar, ...).
##############################################################################

# --- PubMed
def esearch_pubmed(query: str, max_results=100, timeout=10):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def parse_efetch_response(xml_text: str) -> dict:
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
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml"
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return parse_efetch_response(r.text)
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Abstracts via EFetch: {e}")
        return {}

def get_pubmed_details(pmids: list):
    if not pmids:
        return []
    url_summary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json"
    }
    try:
        r_sum = requests.get(url_summary, params=params_sum, timeout=10)
        r_sum.raise_for_status()
        data_summary = r_sum.json()
    except Exception as e:
        st.error(f"Fehler beim Abrufen von PubMed-Daten (ESummary): {e}")
        return []

    abstracts_map = fetch_pubmed_abstracts(pmids, timeout=10)

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

        full_data = dict(info)
        full_data["abstract"] = abs_text

        results.append({
            "Source": "PubMed",
            "Title": title,
            "PubMed ID": pmid,
            "Abstract": abs_text,
            "DOI": doi,
            "Year": pubyear,
            "Publisher": publisher,
            "Population": "n/a",
            "FullData": full_data
        })
    return results

def search_pubmed(query: str, max_results=100):
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

# --- Europe PMC
def search_europe_pmc(query: str, max_results=100, timeout=30, retries=3, delay=5):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results
    }
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            results = []
            for item in data.get("resultList", {}).get("result", []):
                pub_year = str(item.get("pubYear", "n/a"))
                abstract_text = item.get("abstractText", "n/a")
                publisher = "n/a"
                jinfo = item.get("journalInfo", {})
                if isinstance(jinfo, dict):
                    publisher = jinfo.get("journal", "n/a")

                results.append({
                    "Source": "Europe PMC",
                    "Title": item.get("title", "n/a"),
                    "PubMed ID": item.get("pmid", "n/a"),
                    "Abstract": abstract_text,
                    "DOI": item.get("doi", "n/a"),
                    "Year": pub_year,
                    "Publisher": publisher,
                    "Population": "n/a",
                    "FullData": dict(item)
                })
            return results
        except requests.exceptions.ReadTimeout:
            st.warning(f"Europe PMC: Read Timeout (Versuch {attempt+1}/{retries}). {delay}s warten ...")
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
            return []
    st.error("Europe PMC-Suche wiederholt fehlgeschlagen (Timeout).")
    return []

# --- Google Scholar
def search_google_scholar(query: str, max_results=100):
    results = []
    try:
        search_results = scholarly.search_pubs(query)
        for _ in range(max_results):
            publication = next(search_results, None)
            if not publication:
                break
            bib = publication.get('bib', {})
            title = bib.get('title', 'n/a')
            pub_year = bib.get('pub_year', 'n/a')
            abstract = bib.get('abstract', 'n/a')

            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract,
                "DOI": "n/a",
                "Year": str(pub_year),
                "Publisher": "n/a",
                "Population": "n/a",
                "FullData": dict(publication)
            })
    except Exception as e:
        st.error(f"Fehler bei der Google Scholar-Suche: {e}")
    return results

# --- Semantic Scholar
def search_semantic_scholar(query: str, max_results=100, retries=3, delay=5):
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,abstract"
    }
    attempt = 0
    results = []
    while attempt < retries:
        try:
            r = requests.get(base_url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            papers = data.get("data", [])
            for paper in papers:
                year_ = str(paper.get("year", "n/a"))
                abstract_ = paper.get("abstract", "n/a")

                results.append({
                    "Source": "Semantic Scholar",
                    "Title": paper.get("title", "n/a"),
                    "PubMed ID": "n/a",
                    "Abstract": abstract_,
                    "DOI": "n/a",
                    "Year": year_,
                    "Publisher": "n/a",
                    "Population": "n/a",
                    "FullData": dict(paper)
                })
            return results
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                st.warning(f"Rate limit bei Semantic Scholar erreicht, warte {delay} Sekunden ...")
                time.sleep(delay)
                attempt += 1
                continue
            else:
                st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
                return []
        except Exception as e:
            st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
            return []
    st.error("Semantic Scholar: Rate limit überschritten.")
    return results

# --- OpenAlex
def search_openalex(query: str, max_results=100):
    base_url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results
    }
    try:
        r = requests.get(base_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        works = data.get("results", [])
        results = []
        for work in works:
            title = work.get("display_name", "n/a")
            publication_year = str(work.get("publication_year", "n/a"))
            doi = work.get("doi", "n/a")
            abstract = "n/a"
            publisher = "n/a"
            full_data = dict(work)

            results.append({
                "Source": "OpenAlex",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract,
                "DOI": doi,
                "Year": publication_year,
                "Publisher": publisher,
                "Population": "n/a",
                "FullData": full_data
            })
        return results
    except Exception as e:
        st.error(f"Fehler bei der OpenAlex-Suche: {e}")
        return []

##############################################################################
# Profil-Verwaltung (optional)
##############################################################################
def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        if profile_name in profiles:
            return profiles[profile_name]
    return None

##############################################################################
# Modul-Funktion (wird in main() aufgerufen)
##############################################################################
def module_codewords_pubmed():
    st.title("Multi-API-Suche + ChatGPT-Paper-Download-Link in Excel")

    # Profil wählen (Demo)
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile in session_state['profiles'].")
        return
    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte ein Profil auswählen.")
        return

    profile_data = load_settings(chosen_profile)
    st.json(profile_data)

    # Eingabe Codewörter
    codewords_str = st.text_input("Codewörter (kommasepariert/Leerzeichen):", "")
    logic_option = st.radio("Logik:", ["AND","OR"], index=1)

    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option=="AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        if profile_data.get("use_pubmed", False):
            pubs = search_pubmed(query_str, max_results=50)
            st.write(f"PubMed: {len(pubs)} Treffer.")
            results_all.extend(pubs)

        if profile_data.get("use_epmc", False):
            epmc = search_europe_pmc(query_str, max_results=50)
            st.write(f"Europe PMC: {len(epmc)} Treffer.")
            results_all.extend(epmc)

        if profile_data.get("use_google", False):
            goo = search_google_scholar(query_str, max_results=50)
            st.write(f"Google Scholar: {len(goo)} Treffer.")
            results_all.extend(goo)

        if profile_data.get("use_semantic", False):
            sem = search_semantic_scholar(query_str, max_results=50)
            st.write(f"Semantic Scholar: {len(sem)} Treffer.")
            results_all.extend(sem)

        if profile_data.get("use_openalex", False):
            oa = search_openalex(query_str, max_results=50)
            st.write(f"OpenAlex: {len(oa)} Treffer.")
            results_all.extend(oa)

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
            return

        # Speichern
        st.session_state["search_results"] = results_all

    if "search_results" in st.session_state and st.session_state["search_results"]:
        results_all = st.session_state["search_results"]
        df_main = pd.DataFrame([{
            "Title": p.get("Title","n/a"),
            "PubMed ID": p.get("PubMed ID","n/a"),
            "Year": p.get("Year","n/a"),
            "Publisher": p.get("Publisher","n/a"),
            "Population": p.get("Population","n/a"),
            "Source": p.get("Source","n/a"),
            "Abstract": p.get("Abstract","n/a")
        } for p in results_all])

        st.dataframe(df_main)

        # Filter
        adv_filter = st.checkbox("Erweiterte Filter?")
        if adv_filter:
            text_filter = st.text_input("Suchbegriff in Title/Publisher (Filter):", "")
            year_list = ["Alle"]+[str(y) for y in range(1900,2026)]
            year_choice = st.selectbox("Jahr:", year_list)

            df_filt = df_main.copy()
            if text_filter.strip():
                tf = text_filter.lower()
                def match_f(r):
                    t = (r["Title"] or "").lower()
                    p = (r["Publisher"] or "").lower()
                    return (tf in t) or (tf in p)
                df_filt = df_filt[df_filt.apply(match_f, axis=1)]
            if year_choice!="Alle":
                df_filt = df_filt[df_filt["Year"]==year_choice]

            st.write("Gefilterte Paper:")
            st.dataframe(df_filt)

            # MultiSelect => ChatGPT generieren
            df_filt["identifier"] = df_filt.apply(lambda r: f"{r['Title']}||{r['PubMed ID']}", axis=1)
            chosen_ids = st.multiselect("Paper auswählen für ChatGPT-Paper?", df_filt["identifier"].tolist())

            if st.button("ChatGPT-Paper generieren & Download ZIP"):
                if not chosen_ids:
                    st.warning("Keine Auswahl.")
                else:
                    # 1) Hole die Paper aus results_all
                    chosen_papers = []
                    for cid in chosen_ids:
                        row = df_filt.loc[df_filt["identifier"]==cid].iloc[0]
                        found=None
                        for rp in results_all:
                            if rp["Title"]==row["Title"] and rp["PubMed ID"]==row["PubMed ID"]:
                                found=rp
                                break
                        if found:
                            chosen_papers.append(found)

                    if not chosen_papers:
                        st.warning("Nichts gefunden.")
                    else:
                        # 2) Erzeuge ChatGPT-"Paper", speichere PDF in ZIP
                        zip_buf = io.BytesIO()
                        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                            for pap in chosen_papers:
                                # Prompt
                                prompt_str = (
                                    f"Erstelle eine wissenschaftliche Zusammenfassung (Paper-Stil) "
                                    f"zu folgendem Titel:\n'{pap['Title']}'.\n\n"
                                    f"Der Abstract lautet:\n{pap['Abstract']}\n\n"
                                    f"Beziehe ggf. Jahr, Population, Publisher etc. mit ein."
                                )
                                gpt_text = generate_chatgpt_paper(prompt_str)
                                if gpt_text:
                                    pdf_io = io.BytesIO()
                                    # PDF
                                    create_gpt_paper_pdf(gpt_text, pdf_io, title="ChatGPT-Paper zu: "+pap['Title'][:30])
                                    pdf_file_name = _sanitize_filename(pap['Title'][:50])+"_gpt.pdf"
                                    zf.writestr(pdf_file_name, pdf_io.getvalue())

                        zip_buf.seek(0)
                        zip_name = f"chatgpt_papers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                        st.download_button(
                            "ChatGPT-Paper-ZIP herunterladen",
                            data=zip_buf.getvalue(),
                            file_name=zip_name,
                            mime="application/octet-stream"
                        )

        # Excel-Export mit Link-Spalte
        st.write("---")
        st.subheader("Excel-Export (mit ChatGPT-Link-Spalte)")

        codewords_ = "Suchbegriffe"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_name = f"{codewords_}_{stamp}.xlsx"

        # Beispiel: Link kann man als "lokaler PDF-Name" oder als "=HYPERLINK()"
        # Hier nur demonstration: "ChatGPT_Paper_Link" => f"=HYPERLINK(\"{some_path}\",\"Download\")"
        # In einer realen Deployment-Umgebung bräuchte man einen Web-Server-Pfad.

        # Hier bauen wir DF + extra Spalte "ChatGPT Paper Link" (Beispiel).
        df_excel = df_main.copy()
        df_excel["ChatGPT_Paper_Link"] = "n/a"  # oder HYPERLINK

        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter
        from openpyxl import load_workbook
        import openpyxl

        from openpyxl.styles import Font

        from openpyxl import Workbook
        wb = Workbook()
        ws_main = wb.active
        ws_main.title = "Main"

        headers = ["Title","PubMed ID","Abstract","Year","Publisher","Population","Source","ChatGPT_Paper_Link"]
        ws_main.append(headers)

        for idx, row in df_excel.iterrows():
            row_list = [
                row["Title"],
                row["PubMed ID"],
                row["Abstract"],
                row["Year"],
                row["Publisher"],
                row["Population"],
                row["Source"],
                row["ChatGPT_Paper_Link"]
            ]
            ws_main.append(row_list)

        # Save
        wb.save(excel_name)
        with open(excel_name,"rb") as f:
            st.download_button(
                "Excel herunterladen",
                data=f,
                file_name=excel_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

##############################################################################
# Haupt-Streamlit: Tabs
##############################################################################
def main():
    st.title("Gesamt-App: ChatGPT + Multi-API")
    # Minimales Profiles-Dummy
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {
            "Default": {
                "use_pubmed": True,
                "use_epmc": True,
                "use_google": True,
                "use_semantic": True,
                "use_openalex": True
            }
        }

    module_codewords_pubmed()

if __name__=="__main__":
    st.set_page_config(layout="wide")
    # openai.api_key = "sk-XXXX"  # <--- HIER DEIN KEY
    main()
