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

# Google Scholar
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
        st.error(f"Fehler bei ChatGPT-API: '{e}' – Prüfe, ob 'OPENAI_API_KEY' in secrets.toml hinterlegt ist!")
        return ""


def save_text_as_pdf(text, pdf_path, title="Paper"):
    """Speichert den Text in ein PDF (lokal)."""
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
# B) arXiv-Suche
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
# C) Multi-API-Suche (PubMed, etc.)
###############################################################################
def flatten_dict(d, parent_key="", sep="__"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


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
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    try:
        r_sum = requests.get(url, params=params_sum, timeout=10)
        r_sum.raise_for_status()
        data_summary = r_sum.json()
    except Exception as e:
        st.error(f"Fehler bei PubMed-ESummary: {e}")
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
                "Abstract": abstract_ or "(n/a)",
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
                "Abstract": abstract_ or "(n/a)",
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
            abstract_ = "(n/a)"
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
# D) ChatGPT-Summary PDF (optional)
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
# E) "Profiles" laden
###############################################################################
def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
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
# G) ChatGPT-Scoring (inkl. Genes)
###############################################################################
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    """
    Schleife über Papers mit eigener 'Fortschritt'-Anzeige in Expander.
    Falls 'genes' vorhanden ist, fließt das in den Prompt ein.
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
    genes_str = ", ".join(genes) if genes else ""

    for idx, paper in enumerate(papers, start=1):
        paper_title = paper.get('Title', '(kein Titel)')
        paper_status.write(f"Paper {idx}/{total}: **{paper_title}**")

        prompt_text = (
            f"Codewörter: {codewords}\n"
            f"Gene: {genes_str}\n\n"
            f"Paper:\n"
            f"Titel: {paper_title}\n"
            f"Abstract:\n{paper.get('Abstract','(kein Abstract)')}\n\n"
            "Gib mir eine Zahl von 0 bis 100 (Relevanz), wobei Codewörter und Gene berücksichtigt werden."
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
            score = int(match.group(1)) if match else 0
        except Exception as e:
            st.error(f"Fehler in ChatGPT-Scoring: {e}")
            score = 0

        new_p = dict(paper)
        new_p["Relevance"] = score
        results_scored.append(new_p)

    results_scored.sort(key=lambda x: x["Relevance"], reverse=True)
    return results_scored[:top_k]


###############################################################################
# H) Excel-Vorlage vorlage_paperqa2.xlsx befüllen
###############################################################################
def fill_excel_paperqa2(gene_name, rs_number, special_comment):
    """
    Öffnet vorlage_paperqa2.xlsx,
    schreibt:
      - Spalte C, Zeile 5 => gene_name  (iat[4,2])
      - Spalte D, Zeile 6 => rs_number  (iat[5,3])
      - Spalte D, Zeile 7 => special_comment (iat[6,3])
    und bietet die angepasste Excel als Download an.
    """
    template_path = "vorlage_paperqa2.xlsx"
    if not os.path.exists(template_path):
        st.error(f"Excel-Vorlage '{template_path}' nicht gefunden.")
        return

    try:
        df = pd.read_excel(template_path, sheet_name=0, header=None)
    except Exception as e:
        st.error(f"Fehler beim Öffnen von '{template_path}': {e}")
        return

    # Nur als Beispiel, du hast 0-basierte Indizes => row 5=4, col C=2, etc.
    # => row 6=5, col D=3
    # => row 7=6, col D=3
    try:
        df.iat[4, 2] = gene_name
        df.iat[5, 3] = rs_number
        df.iat[6, 3] = special_comment
    except Exception as e:
        st.error(f"Fehler beim Eintragen in die Excel: {e}")
        return

    # Jetzt in Memory speichern + Download-Button
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")
    output.seek(0)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vorlage_paperqa2_COMPLETED_{now}.xlsx"

    st.download_button(
        label="Fertige Excel herunterladen",
        data=output,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


###############################################################################
# I) Modul für Multi-API-Suche + ChatGPT + Excel-Befüllung
###############################################################################
def module_codewords_pubmed():
    st.title("Multi-API-Suche + Genes + ChatGPT => Excel 'vorlage_paperqa2.xlsx' füllen")

    # Profile check
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile.")
        return

    prof_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + prof_names)
    if chosen_profile == "(kein)":
        st.info("Kein Profil gewählt.")
        return

    profile_data = load_settings(chosen_profile)
    st.json(profile_data)

    # Codewords + Genes
    codewords_str = st.text_input("Codewörter:", profile_data.get("codewords",""))
    logic_option = st.radio("AND/OR?", ["AND","OR"], 1)
    genes = profile_data.get("genes", [])
    st.write(f"Profil-Genes: {genes}")

    if st.button("API-Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]

        # Logik
        if logic_option == "AND":
            query_str = " AND ".join(raw_list) if raw_list else ""
        else:
            query_str = " OR ".join(raw_list) if raw_list else ""

        if genes:
            genes_query = " OR ".join(genes)
            if query_str.strip():
                query_str = f"({query_str}) OR ({genes_query})"
            else:
                query_str = genes_query

        if not query_str.strip():
            st.warning("Keine Codewords + Genes => Abbruch.")
            return

        st.write("Finale Anfrage:", query_str)

        results_all = []

        if profile_data.get("use_pubmed", False):
            pm = search_pubmed(query_str, max_results=200)
            st.write(f"PubMed: {len(pm)}")
            results_all.extend(pm)

        if profile_data.get("use_epmc", False):
            ep = search_europe_pmc(query_str, max_results=200)
            st.write(f"Europe PMC: {len(ep)}")
            results_all.extend(ep)

        if profile_data.get("use_google", False):
            gg = search_google_scholar(query_str, max_results=200)
            st.write(f"Google Scholar: {len(gg)}")
            results_all.extend(gg)

        if profile_data.get("use_semantic", False):
            se = search_semantic_scholar(query_str, max_results=200)
            st.write(f"Semantic Scholar: {len(se)}")
            results_all.extend(se)

        if profile_data.get("use_openalex", False):
            oa = search_openalex(query_str, max_results=200)
            st.write(f"OpenAlex: {len(oa)}")
            results_all.extend(oa)

        # Max 1000
        if len(results_all) > 1000:
            results_all = results_all[:1000]

        if not results_all:
            st.info("Nichts gefunden.")
            return

        st.session_state["search_results"] = results_all
        st.write(f"Insgesamt {len(results_all)} Papers gefunden.")

    if "search_results" in st.session_state and st.session_state["search_results"]:
        df_main = pd.DataFrame(st.session_state["search_results"])
        st.dataframe(df_main)

        if st.button("ChatGPT => top 100 => Excel"):
            top100 = chatgpt_online_search_with_genes(
                st.session_state["search_results"],
                codewords=codewords_str,
                genes=genes,
                top_k=100
            )
            if not top100:
                st.warning("Keine top 100 gefunden.")
            else:
                st.write("Top 100 Paper (nach ChatGPT-Relevanz):")
                df_top = pd.DataFrame(top100)
                st.dataframe(df_top)

                # Excel-Befüllung
                st.subheader("Trage Gene-Name, RS-Nummer, Special Comment in Excel ein:")
                gene_input = st.text_input("Gene-Name (für Spalte C, Zeile 5)", "")
                rs_input = st.text_input("RS-Nummer (für Spalte D, Zeile 6)", "")
                comment_input = st.text_input("Special Comment (für Spalte D, Zeile 7)", "")

                if st.button("vorlage_paperqa2.xlsx befüllen + Download"):
                    fill_excel_paperqa2(gene_input, rs_input, comment_input)


###############################################################################
# J) Haupt-App
###############################################################################
def main():
    st.title("Kombinierte App: ChatGPT-Paper, arXiv, Multi-API-Suche + Genes => Excel-Befüllung")

    if "profiles" not in st.session_state:
        # Beispielhaftes Default-Profil
        st.session_state["profiles"] = {
            "DefaultProfile": {
                "use_pubmed": True,
                "use_epmc": True,
                "use_google": True,
                "use_semantic": True,
                "use_openalex": True,
                "genes": ["BRCA1", "TP53"],
                "codewords": "Cancer therapy"
            }
        }

    menu = ["ChatGPT-Paper", "arXiv-Suche", "Multi-API+Genes+Excel"]
    choice = st.sidebar.selectbox("Navigation", menu)

    if choice == "ChatGPT-Paper":
        st.subheader("Paper mit ChatGPT generieren & lokal speichern")
        prompt_txt = st.text_area("Prompt:", "Schreibe ein Paper über KI in der Medizin.")
        local_dir = st.text_input("Zielordner lokal:", "chatgpt_papers")

        if st.button("Paper generieren"):
            text = generate_paper_via_chatgpt(prompt_txt)
            if text:
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                now_ = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_name = f"chatgpt_paper_{now_}.pdf"
                pdf_path = os.path.join(local_dir, pdf_name)
                save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper")
                st.success(f"Paper gespeichert unter: {pdf_path}")

    elif choice == "arXiv-Suche":
        st.subheader("arXiv-Suche & PDF-Download (lokal)")
        query = st.text_input("Suchbegriff (arXiv):", "quantum computing")
        num = st.number_input("Anzahl Ergebnisse", 1, 50, 5)
        local_dir_arxiv = st.text_input("Downloads-Ordner:", "arxiv_papers")

        if st.button("arXiv-Suche starten"):
            results = search_arxiv_papers(query, max_results=num)
            if not results:
                st.info("Keine Treffer.")
            else:
                st.write(f"{len(results)} Treffer gefunden:")
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
        module_codewords_pubmed()


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    main()
