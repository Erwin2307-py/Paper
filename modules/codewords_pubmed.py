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

try:
    from scholarly import scholarly
except ImportError:
    st.error("Bitte installiere 'scholarly', z.B. via: pip install scholarly")

import openai
try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf', z.B. mit: pip install fpdf")

###############################################################################
# A) ChatGPT: Paper erstellen & lokal speichern
###############################################################################
def generate_paper_via_chatgpt(prompt_text, model="gpt-3.5-turbo"):
    """Ruft die ChatGPT-API auf und erzeugt ein Paper (Text)."""
    try:
        openai.api_key = st.secrets["OPENAI_API_KEY"]  # Holt KEY aus secrets
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(
            "Fehler bei ChatGPT-API: "
            f"'{e}'.\nPrüfe, ob 'OPENAI_API_KEY' in secrets.toml hinterlegt ist!"
        )
        return ""


def save_text_as_pdf(text, pdf_path, title="Paper"):
    """Speichert den gegebenen Text in ein PDF (lokal)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)

    lines = text.split("\n")
    for line in lines:
        pdf.multi_cell(0, 8, line)
        pdf.ln(2)

    pdf.output(pdf_path, "F")


###############################################################################
# B) arXiv-Suche & Download & lokal speichern
###############################################################################
def search_arxiv_papers(query, max_results=5):
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
# C) Multi-API-Suche
###############################################################################
def flatten_dict(d, parent_key="", sep="__"):
    """Wandelt ein verschachteltes Dict in ein flaches Dict um."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


# --- PubMed-Funktionen ---
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
    """Holt Abstracts per efetch."""
    if not pmids:
        return {}
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
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
    params_sum = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    try:
        r_sum = requests.get(url_summary, params=params_sum, timeout=10)
        r_sum.raise_for_status()
        data_summary = r_sum.json()
    except Exception as e:
        st.error(f"Fehler bei der PubMed-ESummary-Anfrage: {e}")
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


# --- Europe PMC ---
def search_europe_pmc(query: str, max_results=100, timeout=10):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": max_results}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        results = []
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
                "Population": "n/a",
                "FullData": dict(item)
            })
        return results
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return []


# --- Google Scholar ---
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
                "Population": "n/a",
                "FullData": dict(pub)
            })
        return results
    except Exception as e:
        st.error(f"Google Scholar-Suche fehlgeschlagen: {e}")
        return []


# --- Semantic Scholar ---
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
                "Population": "n/a",
                "FullData": dict(p)
            })
        return results
    except Exception as e:
        st.error(f"Semantic Scholar-Suche fehlgeschlagen: {e}")
        return []
    return results


# --- OpenAlex ---
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
                "Population": "n/a",
                "FullData": dict(w)
            })
        return results
    except Exception as e:
        st.error(f"OpenAlex-Suche fehlgeschlagen: {e}")
        return results


###############################################################################
# D) ChatGPT-Summary PDF
###############################################################################
def create_gpt_paper_pdf(gpt_text, output_stream, title="ChatGPT-Paper"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
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


###############################################################################
# E) "Profiles" laden (optional)
###############################################################################
def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        return profiles.get(profile_name, None)
    return None


###############################################################################
# F) Helper
###############################################################################
def safe_excel_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


###############################################################################
# G) ChatGPT-Scoring in extra Fenster + Genes-Check
###############################################################################
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    """
    Schleife über Papers mit einer ChatGPT-Abfrage, um eine Relevanz (0-100) zu erhalten.
    Falls 'genes' vorhanden ist, fließt das in den Prompt mit ein.
    """
    if not papers:
        return []

    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("Kein 'OPENAI_API_KEY' in st.secrets! Abbruch.")
        return []

    progress_area = st.expander("Fortschritt (aktuelles Paper)", expanded=True)
    paper_status = progress_area.empty()

    results_scored = []
    total = len(papers)

    # Gene-Liste in String fassen:
    genes_str = ", ".join(genes) if genes else ""

    # Codewörter
    code_str = codewords if codewords else ""

    for idx, paper in enumerate(papers, start=1):
        paper_title = paper.get('Title', '(kein Titel)')
        paper_status.write(f"Paper {idx}/{total}: **{paper_title}**")

        # Prompt:
        prompt_text = (
            f"Codewörter: {code_str}\n"
            f"Gene: {genes_str}\n\n"
            f"Paper:\n"
            f"Titel: {paper_title}\n"
            f"Abstract:\n{paper.get('Abstract','(kein Abstract)')}\n\n"
            "Gib mir eine Zahl von 0 bis 100 (Relevanz), wobei sowohl Codewörter als auch Gene berücksichtigt werden."
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=20,
                temperature=0
            )
            raw_text = response.choices[0].message.content.strip()
            match = re.search(r'(\d+)', raw_text)
            if match:
                score = int(match.group(1))
            else:
                score = 0
        except Exception as e:
            st.error(f"Fehler bei ChatGPT-Scoring: {e}")
            score = 0

        new_p = dict(paper)
        new_p["Relevance"] = score
        results_scored.append(new_p)

    results_scored.sort(key=lambda x: x["Relevance"], reverse=True)
    return results_scored[:top_k]


###############################################################################
# H) Multi-API-Suche + ChatGPT mit Genes (aus Profil)
###############################################################################
def module_codewords_pubmed():
    st.title("Multi-API-Suche (PubMed, Europe PMC, Google Scholar, ...) + ChatGPT-Scoring (Genes + Codewörter)")

    # Prüfen, ob Profile existieren
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile hinterlegt oder SessionState leer.")
        return

    prof_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + prof_names)
    if chosen_profile == "(kein)":
        st.info("Kein Profil gewählt. -> Abbruch.")
        return

    # Profil laden
    profile_data = load_settings(chosen_profile)
    if not profile_data:
        st.warning("Profil nicht gefunden oder leer.")
        return

    st.write("Profil-Daten:", profile_data)

    # Codewörter aus Profil oder leer
    default_codewords = profile_data.get("codewords", "")
    codewords_str = st.text_input("Codewörter (werden mit Genes kombiniert):", value=default_codewords)
    genes_from_profile = profile_data.get("genes", [])

    st.write(f"Genes aus Profil: {genes_from_profile}")

    # Logik wählbar
    logic_option = st.radio("Logik für Codewörter + Gene in der finalen Suche:", ["OR", "AND"], index=0)

    if st.button("Suche starten"):
        # 1) Codewörter in Liste
        raw_words_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        # 2) Genes in Liste
        raw_genes_list = genes_from_profile

        if not raw_words_list and not raw_genes_list:
            st.warning("Keine Codewörter und keine Gene -> Suche nicht möglich.")
            return

        # Finale Query bilden
        if logic_option == "OR":
            query_codewords = " OR ".join(raw_words_list) if raw_words_list else ""
            query_genes = " OR ".join(raw_genes_list) if raw_genes_list else ""
            if query_codewords and query_genes:
                final_query = f"({query_codewords}) OR ({query_genes})"
            else:
                final_query = query_codewords or query_genes
        else:
            # AND
            query_codewords = " AND ".join(raw_words_list) if raw_words_list else ""
            query_genes = " AND ".join(raw_genes_list) if raw_genes_list else ""
            if query_codewords and query_genes:
                final_query = f"({query_codewords}) AND ({query_genes})"
            else:
                final_query = query_codewords or query_genes

        st.write("Finale Suchanfrage:", final_query)

        results_all = []

        if profile_data.get("use_pubmed", False):
            pm = search_pubmed(final_query, max_results=200)
            st.write(f"PubMed: {len(pm)}")
            results_all.extend(pm)

        if profile_data.get("use_epmc", False):
            ep = search_europe_pmc(final_query, max_results=200)
            st.write(f"Europe PMC: {len(ep)}")
            results_all.extend(ep)

        if profile_data.get("use_google", False):
            gg = search_google_scholar(final_query, max_results=200)
            st.write(f"Google Scholar: {len(gg)}")
            results_all.extend(gg)

        if profile_data.get("use_semantic", False):
            se = search_semantic_scholar(final_query, max_results=200)
            st.write(f"Semantic Scholar: {len(se)}")
            results_all.extend(se)

        if profile_data.get("use_openalex", False):
            oa = search_openalex(final_query, max_results=200)
            st.write(f"OpenAlex: {len(oa)}")
            results_all.extend(oa)

        if not results_all:
            st.info("Keine Treffer gefunden.")
            return

        # Auf 1000 beschränken
        if len(results_all) > 1000:
            results_all = results_all[:1000]

        st.session_state["search_results"] = results_all
        st.write(f"Gefundene Papers insgesamt: {len(results_all)}")

    # Falls Ergebnisse in der Session
    if "search_results" in st.session_state and st.session_state["search_results"]:
        all_papers = st.session_state["search_results"]
        df_main = pd.DataFrame(all_papers)
        st.dataframe(df_main)

        st.write("---")
        st.subheader("ChatGPT-Online-Filterung nach Relevanz (Genes + Codewords)")

        ### NEU: Zeige an, welche Kriterien laut Profil verwendet werden ###
        st.markdown(f"**Im Profil hinterlegte Kriterien:**  \n"
                    f"- **Codewords**: {codewords_str}  \n"
                    f"- **Gene**: {', '.join(genes_from_profile) if genes_from_profile else '(keine)'}")

        if st.button("Starte ChatGPT-Scoring"):
            if not codewords_str.strip() and not genes_from_profile:
                st.warning("Keine Codewords und keine Gene vorhanden -> Abbruch.")
            else:
                st.write("Starte ChatGPT-Scoring...\n")
                top_results = chatgpt_online_search_with_genes(
                    all_papers,
                    codewords=codewords_str,   # Aus dem Textfeld (ggf. Profil)
                    genes=genes_from_profile,  # Immer aus Profil
                    top_k=100                  # Nur Top 100
                )
                if top_results:
                    st.subheader("Top 100 Paper (nach ChatGPT-Relevanz)")
                    df_top = pd.DataFrame(top_results)
                    st.dataframe(df_top)

                    # Button zum lokalen Excel-Export
                    st.write("---")
                    st.subheader("Excel-Export")
                    
                    codew_for_filename = sanitize_filename(codewords_str) or "keine_codewords"
                    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    excel_filename = f"papers_{codew_for_filename}_{time_str}.xlsx"

                    if st.button("Top 100 als Excel speichern (lokal)"):
                        local_dir_excel = "excel_results"
                        if not os.path.exists(local_dir_excel):
                            os.makedirs(local_dir_excel)

                        excel_path = os.path.join(local_dir_excel, excel_filename)

                        df_top_all = pd.DataFrame(top_results)
                        with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
                            for source_name, group_df in df_top_all.groupby("Source"):
                                sheet_name = sanitize_filename(str(source_name))[:31]
                                group_df.to_excel(writer, sheet_name=sheet_name, index=False)

                        st.success(f"Excel gespeichert unter: {excel_path}")


###############################################################################
# I) Haupt-App
###############################################################################
def main():
    st.title("Kombinierte App: ChatGPT-Paper, arXiv-Suche, Multi-API-Suche (Genes+Codewords)")

    # Beispiel-Profil beim ersten Start
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
        st.subheader("1) Paper mit ChatGPT generieren & lokal speichern")
        prompt_txt = st.text_area("Prompt:", "Schreibe ein Paper über KI in der Medizin.")
        local_dir = st.text_input("Zielordner lokal:", "chatgpt_papers")
        if st.button("Paper generieren"):
            text = generate_paper_via_chatgpt(prompt_txt)
            if text:
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_name = f"chatgpt_paper_{time_str}.pdf"
                pdf_path = os.path.join(local_dir, pdf_name)
                save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper")
                st.success(f"Paper gespeichert unter: {pdf_path}")

    elif choice == "arXiv-Suche":
        st.subheader("2) arXiv-Suche & PDF-Download (lokal)")
        query = st.text_input("arXiv Suchbegriff:", "quantum computing")
        num = st.number_input("Anzahl", 1, 50, 5)
        local_dir_arxiv = st.text_input("Ordner für Downloads:", "arxiv_papers")

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
                        st.write("_Kein PDF-Link._")
                    st.write("---")

    else:
        st.subheader("3) Multi-API-Suche (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)")
        module_codewords_pubmed()


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    main()
