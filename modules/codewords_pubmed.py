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
# Wichtig: Den API-Key NICHT hartkodieren, sondern st.secrets["OPENAI_API_KEY"] nutzen.

# PDF-Erzeugung mit fpdf:
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
        openai.api_key = st.secrets["OPENAI_API_KEY"]
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
# C) Multi-API-Suche (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)
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


# --- PubMed ---
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
# D) ChatGPT-Summary PDF
###############################################################################
def create_gpt_paper_pdf(gpt_text, output_stream, title="ChatGPT-Paper"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)
    for line in gpt_text.split("\n"):
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
# G) ChatGPT-Scoring mit Genes (inkl. Fortschrittsanzeige)
###############################################################################
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    """
    Geht alle Papers durch und fragt ChatGPT nach einer Relevanzbewertung.
    Falls 'genes' vorhanden sind, werden diese in den Prompt mit einbezogen.
    Zeigt in einem separaten Expander an, welches Paper aktuell verarbeitet wird.
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
            f"Paper:\nTitel: {paper_title}\nAbstract:\n{paper.get('Abstract', '(kein Abstract)')}\n\n"
            "Bitte gib mir eine Zahl zwischen 0 und 100 als Relevanz, wobei sowohl die Codewörter als auch die Gene berücksichtigt werden."
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
# H) Excel-Vorlage (vorlage_paperqa2.xlsx) befüllen
###############################################################################
def fill_excel_paperqa2(gene_name, rs_number, special_comment):
    """
    Öffnet 'vorlage_paperqa2.xlsx', trägt die Werte ein und stellt sie zum Download bereit.
    """
    template_path = "vorlage_paperqa2.xlsx"
    if not os.path.exists(template_path):
        st.error(f"Excel-Vorlage '{template_path}' nicht gefunden.")
        return
    try:
        df = pd.read_excel(template_path, sheet_name=0, header=None)
    except Exception as e:
        st.error(f"Fehler beim Öffnen der Vorlage: {e}")
        return

    try:
        df.iat[4, 2] = gene_name
        df.iat[5, 3] = rs_number
        df.iat[6, 3] = special_comment
    except Exception as e:
        st.error(f"Fehler beim Befüllen der Excel: {e}")
        return

    output = io.BytesIO()
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
# I) PaperQA2 Online Tool: ChatGPT-basiert relevante RS-Nummer und Special Comment
###############################################################################
def run_paperqa2_online_tool():
    st.subheader("PaperQA2 Online Tool")
    # Prüfe, ob Suchergebnisse vorhanden sind
    if "search_results" not in st.session_state or not st.session_state["search_results"]:
        st.warning("Keine Suchergebnisse vorhanden. Führe zuerst die Multi-API-Suche durch.")
        return

    # Frage, wonach gefiltert werden soll (Filterkriterien)
    filter_criteria = st.text_input("Bitte geben Sie die Filterkriterien für PaperQA2 ein (z.B. 'rs number must be associated with high expression'):")

    # Auswahl des Gens aus dem Profil (Dropdown, falls mehr als ein Gen im Profil; ansonsten direkt)
    profile_data = load_settings(st.session_state["current_settings"].get("profile_name", ""))
    gene_options = profile_data.get("genes", []) if profile_data and "genes" in profile_data else []
    if not gene_options:
        st.warning("Kein Gen im Profil vorhanden. Bitte fügen Sie ein Gen in das Profil ein.")
        return
    elif len(gene_options) == 1:
        selected_gene = gene_options[0]
    else:
        selected_gene = st.selectbox("Wählen Sie das Gen aus, für das die RS-Nummer gesucht werden soll:", gene_options)

    # Optionale Anzeige: Wie soll PaperQA2 filtern? (z.B. nach Titel, Abstract, etc.)
    additional_filter = st.text_input("Weitere spezifische Filter (optional):", "")

    if st.button("PaperQA2 Online starten"):
        # Nutze als Input für ChatGPT die Top 100 Paper aus den Suchergebnissen
        if "search_results" in st.session_state:
            papers = st.session_state["search_results"][:100]  # Top 100
        else:
            st.warning("Keine Suchergebnisse vorhanden.")
            return

        # Baue einen Prompt für ChatGPT
        paper_summaries = "\n".join(
            [f"- {p.get('Title','n/a')}: {p.get('Abstract','(kein Abstract)')}" for p in papers]
        )
        prompt = (
            f"Du bist ein wissenschaftlicher Assistent.\n"
            f"Gegeben ist das Gen: {selected_gene}\n"
            f"Filterkriterien: {filter_criteria}\n"
            f"Weitere Filter: {additional_filter}\n\n"
            f"Die folgenden 100 Paper (Titel und Abstracts) wurden aus einer API-Suche ermittelt:\n"
            f"{paper_summaries}\n\n"
            "Bitte analysiere diese Liste und nenne mir als Ergebnis die am relevantesten erscheinende RS-Nummer für das Gen "
            f"{selected_gene} sowie einen kurzen Kommentar, der deine Auswahl begründet. Gib die Antwort in folgendem Format aus:\n\n"
            "RS-Nummer: [rsNummer]\nKommentar: [Special Comment]"
        )

        st.write("ChatGPT-PaperQA2 Tool wird gestartet...")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0
            )
            answer = response.choices[0].message.content.strip()
            st.write("ChatGPT-Antwort:")
            st.code(answer)
            # RS-Nummer und Kommentar extrahieren
            rs_match = re.search(r'RS-Nummer:\s*(\S+)', answer)
            comment_match = re.search(r'Kommentar:\s*(.+)', answer)
            rs_number = rs_match.group(1) if rs_match else "n/a"
            special_comment = comment_match.group(1) if comment_match else "n/a"
            st.success(f"RS-Nummer: {rs_number}\nSpecial Comment: {special_comment}")
            fill_excel_paperqa2(selected_gene, rs_number, special_comment)
        except Exception as e:
            st.error(f"Fehler beim PaperQA2 Online Tool: {e}")


###############################################################################
# Zusätzliche Funktion für die Multi-API-Suche via Codewörter und Profil-Einstellungen
###############################################################################
def module_codewords_pubmed():
    st.subheader("Multi-API-Suche mit Codewörtern & Genen (PubMed, Europe PMC, Google Scholar, Semantic Scholar, OpenAlex)")

    profile_name = st.session_state["current_settings"].get("profile_name", "DefaultProfile")
    profile_data = load_settings(profile_name)
    if not profile_data:
        st.warning("Kein Profil gefunden. Bitte Profil anlegen.")
        return

    codewords = st.text_input("Codewörter:", profile_data.get("codewords", ""))
    st.session_state["current_settings"]["codewords"] = codewords  # Speichern des aktuellen Werts
    genes = profile_data.get("genes", [])

    st.write(f"Aktives Profil: {profile_name}")
    st.write(f"Gene: {genes}")

    use_pubmed = st.checkbox("PubMed nutzen", value=profile_data.get("use_pubmed", True))
    use_epmc = st.checkbox("Europe PMC nutzen", value=profile_data.get("use_epmc", True))
    use_google = st.checkbox("Google Scholar nutzen", value=profile_data.get("use_google", True))
    use_semantic = st.checkbox("Semantic Scholar nutzen", value=profile_data.get("use_semantic", True))
    use_openalex = st.checkbox("OpenAlex nutzen", value=profile_data.get("use_openalex", True))

    max_results = st.number_input("Max. Ergebnisse pro Quelle:", min_value=1, max_value=1000, value=50)

    if st.button("Multi-API-Suche starten"):
        all_results = []
        if use_pubmed:
            pubmed_results = search_pubmed(codewords, max_results=max_results)
            all_results.extend(pubmed_results)
        if use_epmc:
            epmc_results = search_europe_pmc(codewords, max_results=max_results)
            all_results.extend(epmc_results)
        if use_google:
            google_results = search_google_scholar(codewords, max_results=max_results)
            all_results.extend(google_results)
        if use_semantic:
            semsch_results = search_semantic_scholar(codewords, max_results=max_results)
            all_results.extend(semsch_results)
        if use_openalex:
            openalex_results = search_openalex(codewords, max_results=max_results)
            all_results.extend(openalex_results)

        st.session_state["search_results"] = all_results
        st.success(f"Suche abgeschlossen. Gefundene Papers: {len(all_results)}.")
        if all_results:
            df = pd.DataFrame(all_results)
            st.write("Erste 10 Treffer:")
            st.dataframe(df.head(10))


###############################################################################
# K) Haupt-App
###############################################################################
def main():
    st.title("Kombinierte App: ChatGPT-Paper, arXiv-Suche, Multi-API-Suche + PaperQA2 Online Tool")

    # Beispiel: Default-Profil, falls noch nicht gesetzt
    if "profiles" not in st.session_state:
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
        st.session_state["current_settings"] = {"profile_name": "DefaultProfile", "codewords": "Cancer therapy", "sheet_choice": ""}

    menu = ["ChatGPT-Paper", "arXiv-Suche", "Multi-API+Genes+PaperQA2"]
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
        st.subheader("Multi-API-Suche + PaperQA2 Online Tool")
        # Multi-API-Suche (PubMed, EPMC, Google Scholar, Semantic Scholar, OpenAlex) + Speicherung in Session
        module_codewords_pubmed()
        st.write("---")
        st.subheader("PaperQA2 Online Tool")
        if st.button("PaperQA2 Online Tool starten"):
            run_paperqa2_online_tool()


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    main()
