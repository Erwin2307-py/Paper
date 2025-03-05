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
    st.error("Bitte installiere 'scholarly', z.B. via: pip install scholarly")

# ChatGPT/OpenAI:
import openai
# Hier kannst du deinen API-Key direkt setzen ODER aus st.secrets holen:
# openai.api_key = "sk-XXX"
# Falls du st.secrets nutzen möchtest:
# openai.api_key = st.secrets["openai_api_key"]

# PDF-Erzeugung mit fpdf
try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf', z.B. mit: pip install fpdf")


###############################################################################
# TEIL A) ChatGPT: Paper erstellen & lokal speichern
###############################################################################
def generate_paper_via_chatgpt(prompt_text, model="gpt-3.5-turbo"):
    """
    Ruft die ChatGPT-API auf und erzeugt ein Paper (Text).
    """
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1200,
            temperature=0.7
        )
        content = response.choices[0].message.content
        return content
    except Exception as e:
        st.error(f"Fehler bei ChatGPT-API: {e}")
        return ""

def save_text_as_pdf(text, pdf_path, title="Paper"):
    """
    Speichert den gegebenen Text in ein PDF unter pdf_path (lokal).
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    # Überschrift
    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)

    # Mehrzeilig: Zeilenweise ins PDF
    lines = text.split("\n")
    for line in lines:
        pdf.multi_cell(0, 8, line)
        pdf.ln(2)

    pdf.output(pdf_path, "F")


###############################################################################
# TEIL B) arXiv-Suche + Download + lokales Speichern
###############################################################################
def search_arxiv_papers(query, max_results=5):
    """
    Sucht über arXiv-API (Atom-Feed), parst Titel, Abstract & PDF-Link.
    """
    base_url = "http://export.arxiv.org/api/query?"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results
    }
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Daten von arXiv: {e}")
        return []
    
    feed = feedparser.parse(response.text)
    papers_info = []

    for entry in feed.entries:
        title = entry.title
        summary = entry.summary
        link_pdf = None
        for link in entry.links:
            if link.rel == "related" and "pdf" in link.type:
                link_pdf = link.href
                break
            elif link.type == "application/pdf":
                link_pdf = link.href
                break
        
        papers_info.append({
            "title": title,
            "summary": summary,
            "pdf_url": link_pdf
        })
    
    return papers_info

def sanitize_filename(fname):
    """Ersetzt unerlaubte Zeichen durch Unterstriche."""
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)

def download_arxiv_pdf(pdf_url, local_filepath):
    """
    Lädt ein PDF von `pdf_url` herunter und speichert es unter `local_filepath`.
    """
    try:
        r = requests.get(pdf_url, timeout=15)
        r.raise_for_status()
        with open(local_filepath, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        st.error(f"Fehler beim Herunterladen der PDF: {e}")
        return False


###############################################################################
# TEIL C) Multi-API-Suche (PubMed, Europe PMC, Google Scholar, ...
###############################################################################

# 1) Flatten Dict (brauchen wir für Excel-Export)
def flatten_dict(d, parent_key="", sep="__"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

# 2) PubMed
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

# 3) Europe PMC
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

# 4) Google Scholar
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

# 5) Semantic Scholar
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

# 6) OpenAlex
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

# 7) Erzeugen einer PDF aus Paper-Daten (Abstract, etc.) -> Bytes
def create_abstract_pdf(paper, output_stream):
    """
    Erstellt ein PDF (Titel, Abstract, etc.) per fpdf in output_stream.
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

    pdf_string = pdf.output(dest='S')
    pdf_bytes = pdf_string.encode('latin-1', 'replace')
    output_stream.write(pdf_bytes)

def _sanitize_filename(fname):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)

def load_settings(profile_name: str):
    """
    Beispiel-Funktion (Profile). Falls du keine Profile nutzt, kannst du das ignorieren.
    """
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        if profile_name in profiles:
            return profiles[profile_name]
    return None

def module_codewords_pubmed():
    st.title("Multi-API-Suche (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)")

    # Profil-Auswahl (falls du so etwas nutzt)
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden (optional).")
        return
    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = load_settings(chosen_profile)
    st.json(profile_data)

    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        if profile_data.get("use_pubmed", False):
            st.write("### PubMed")
            pubmed_res = search_pubmed(query_str, max_results=100)
            st.write(f"Anzahl PubMed-Ergebnisse: {len(pubmed_res)}")
            results_all.extend(pubmed_res)

        if profile_data.get("use_epmc", False):
            st.write("### Europe PMC")
            epmc_res = search_europe_pmc(query_str, max_results=100)
            st.write(f"Anzahl Europe PMC-Ergebnisse: {len(epmc_res)}")
            results_all.extend(epmc_res)

        if profile_data.get("use_google", False):
            st.write("### Google Scholar")
            google_res = search_google_scholar(query_str, max_results=100)
            st.write(f"Anzahl Google Scholar-Ergebnisse: {len(google_res)}")
            results_all.extend(google_res)

        if profile_data.get("use_semantic", False):
            st.write("### Semantic Scholar")
            sem_res = search_semantic_scholar(query_str, max_results=100)
            st.write(f"Anzahl Semantic Scholar-Ergebnisse: {len(sem_res)}")
            results_all.extend(sem_res)

        if profile_data.get("use_openalex", False):
            st.write("### OpenAlex")
            oa_res = search_openalex(query_str, max_results=100)
            st.write(f"Anzahl OpenAlex-Ergebnisse: {len(oa_res)}")
            results_all.extend(oa_res)

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
            return

        st.session_state["search_results"] = results_all

    if "search_results" in st.session_state and st.session_state["search_results"]:
        results_all = st.session_state["search_results"]
        df_main = pd.DataFrame([
            {
                "Title": p.get("Title", "n/a"),
                "PubMed ID": p.get("PubMed ID", "n/a"),
                "Year": p.get("Year", "n/a"),
                "Publisher": p.get("Publisher", "n/a"),
                "Population": p.get("Population", "n/a"),
                "Source": p.get("Source", "n/a"),
                "Abstract": p.get("Abstract", "n/a")
            }
            for p in results_all
        ])
        st.dataframe(df_main)

        st.subheader("Erweiterte Filterung")
        adv_filter = st.checkbox("Filter aktivieren?")

        if adv_filter:
            text_filter = st.text_input("Suchbegriff (Title/Publisher):", "")
            year_list = ["Alle"] + [str(y) for y in range(1900, 2026)]
            year_choice = st.selectbox("Jahr:", year_list)

            df_filtered = df_main.copy()
            if text_filter.strip():
                tf = text_filter.lower()
                def match_filter(r):
                    t = (r["Title"] or "").lower()
                    p = (r["Publisher"] or "").lower()
                    return (tf in t) or (tf in p)
                df_filtered = df_filtered[df_filtered.apply(match_filter, axis=1)]
            if year_choice != "Alle":
                df_filtered = df_filtered[df_filtered["Year"] == year_choice]

            st.dataframe(df_filtered)

            if st.button("Gefilterte Paper in neuem Fenster anschauen"):
                if df_filtered.empty:
                    st.warning("Keine gefilterten Paper.")
                else:
                    filtered_html = df_filtered.to_html(index=False, escape=False)
                    b64_html = base64.b64encode(filtered_html.encode()).decode()
                    html_link = f'<a href="data:text/html;base64,{b64_html}" target="_blank">Gefilterte Paper öffnen</a>'
                    st.markdown(html_link, unsafe_allow_html=True)

            df_filtered["identifier"] = df_filtered.apply(lambda x: f"{x['Title']}||{x['PubMed ID']}", axis=1)
            chosen_ids = st.multiselect("Paper für PDF:", df_filtered["identifier"].tolist())

            if st.button("PDF (ZIP) herunterladen"):
                if not chosen_ids:
                    st.warning("Nichts ausgewählt.")
                else:
                    selected_papers = []
                    for cid in chosen_ids:
                        row = df_filtered.loc[df_filtered["identifier"] == cid].iloc[0]
                        found_paper = None
                        for rp in results_all:
                            if rp["Title"] == row["Title"] and rp["PubMed ID"] == row["PubMed ID"]:
                                found_paper = rp
                                break
                        if found_paper:
                            selected_papers.append(found_paper)

                    if not selected_papers:
                        st.warning("Keine passenden Paper gefunden.")
                    else:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                            for spap in selected_papers:
                                name_sane = _sanitize_filename(spap["Title"][:50])
                                pdf_file = f"{name_sane}.pdf"
                                pdf_bytes_io = io.BytesIO()
                                create_abstract_pdf(spap, pdf_bytes_io)
                                zf.writestr(pdf_file, pdf_bytes_io.getvalue())

                        zip_buffer.seek(0)
                        zip_filename = f"papers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                        st.download_button(
                            "ZIP herunterladen",
                            data=zip_buffer.getvalue(),
                            file_name=zip_filename,
                            mime="application/octet-stream"
                        )

        # Excel-Export
        st.subheader("Excel-Export (alle Paper)")
        codewords_ = "Suchbegriffe"
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fname_xlsx = f"{codewords_}_{timestamp_str}.xlsx"

        from collections import defaultdict
        source_groups = defaultdict(list)
        for p in results_all:
            source_groups[p.get("Source", "n/a")].append(p)

        df_main_excel = df_main[["Title","PubMed ID","Abstract","Year","Publisher","Population","Source"]]

        with pd.ExcelWriter(fname_xlsx, engine="openpyxl") as writer:
            df_main_excel.to_excel(writer, sheet_name="Main", index=False)
            for sname, plist in source_groups.items():
                rows = []
                for p in plist:
                    fd = flatten_dict(p.get("FullData", {}))
                    fd["Title"] = p.get("Title","n/a")
                    fd["PubMed ID"] = p.get("PubMed ID","n/a")
                    fd["Abstract"] = p.get("Abstract","n/a")
                    fd["Year"] = p.get("Year","n/a")
                    fd["Publisher"] = p.get("Publisher","n/a")
                    fd["Population"] = p.get("Population","n/a")
                    fd["Source"] = p.get("Source","n/a")
                    rows.append(fd)
                dfx = pd.DataFrame(rows) if rows else pd.DataFrame()
                short_sname = sname[:31] if sname else "API"
                dfx.to_excel(writer, sheet_name=short_sname, index=False)

        with open(fname_xlsx,"rb") as f:
            st.download_button(
                "Excel-Datei herunterladen",
                data=f,
                file_name=fname_xlsx,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


###############################################################################
# TEIL D) Streamlit-Haupt-App
###############################################################################

def main():
    st.title("Kombinierte App: ChatGPT-Paper, arXiv-Suche, Multi-API-Suche")

    # Tabs oder Seitenaufteilung
    menu = ["ChatGPT-Paper", "arXiv-Suche", "Multi-API-Suche"]
    choice = st.sidebar.selectbox("Navigation", menu)

    if choice == "ChatGPT-Paper":
        st.subheader("Paper mit ChatGPT generieren & lokal speichern")
        prompt_txt = st.text_area("Prompt für ChatGPT:", 
            "Schreibe ein kurzes Paper über die neuesten Erkenntnisse in der Quantencomputing-Forschung.")
        local_dir = st.text_input("Ordner für PDF:", "chatgpt_papers")
        if st.button("Paper generieren"):
            text = generate_paper_via_chatgpt(prompt_txt)
            if text:
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_name = f"chatgpt_paper_{stamp}.pdf"
                pdf_path = os.path.join(local_dir, pdf_name)
                save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper")
                st.success(f"Paper lokal gespeichert unter: {pdf_path}")

    elif choice == "arXiv-Suche":
        st.subheader("arXiv-Suche & PDF-Download (lokal)")
        query = st.text_input("Suchbegriff:", "quantum computing")
        num = st.number_input("Anzahl Ergebnisse", 1, 50, 5)
        local_dir_arxiv = st.text_input("Ordner für arXiv-PDFs:", "arxiv_papers")

        if st.button("arXiv-Suche starten"):
            st.write(f"Suche in arXiv nach: '{query}' (max. {num})")
            papers = search_arxiv_papers(query, max_results=num)
            if not papers:
                st.info("Keine Ergebnisse gefunden oder Fehler.")
            else:
                st.write(f"Gefundene Paper: {len(papers)}")
                if not os.path.exists(local_dir_arxiv):
                    os.makedirs(local_dir_arxiv, exist_ok=True)

                for idx, pap in enumerate(papers, start=1):
                    st.write(f"**{idx}) {pap['title']}**")
                    st.write(pap['summary'][:300] + "...")
                    if pap["pdf_url"]:
                        fname = sanitize_filename(pap["title"])[:50] + ".pdf"
                        full_path = os.path.join(local_dir_arxiv, fname)
                        if st.button(f"PDF herunterladen: {fname}", key=f"arxiv_{idx}"):
                            ok = download_arxiv_pdf(pap["pdf_url"], full_path)
                            if ok:
                                st.success(f"PDF gespeichert: {full_path}")
                    else:
                        st.write("_Kein PDF-Link gefunden_")
                    st.write("---")

    else:
        st.subheader("Multi-API-Suche (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)")

        # (Beispielweise Profile in st.session_state definieren, z.B.:
        # st.session_state["profiles"] = {
        #   "MeinProfil": {
        #       "use_pubmed": True,
        #       "use_epmc": True,
        #       "use_google": True,
        #       "use_semantic": False,
        #       "use_openalex": True
        #   }
        # }
        #)

        module_codewords_pubmed()  # Ruft die Funktion auf


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    # Hier ggf. openai.api_key = "..."
    main()
