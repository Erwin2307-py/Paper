import streamlit as st
import requests
import pandas as pd
import os
import time
import xml.etree.ElementTree as ET
from scholarly import scholarly
from datetime import datetime
from collections import defaultdict
import re
import base64

try:
    import fitz  # PyMuPDF
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fitz' (PyMuPDF) und 'fpdf', z.B.: 'pip install pymupdf fpdf'.")

##############################
# Dict-Flattening
##############################
def flatten_dict(d, parent_key="", sep="__"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

##############################
# PubMed-Funktionen
##############################
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

##############################
# Europe PMC
##############################
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

##############################
# Google Scholar
##############################
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

##############################
# Semantic Scholar
##############################
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

##############################
# OpenAlex
##############################
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

##############################
# CORE
##############################
def search_core(query: str, max_results=100):
    """
    Hier ggf. an CORE-API anbinden.
    """
    return [{
        "Source": "CORE",
        "Title": "Dummy Title from CORE",
        "PubMed ID": "n/a",
        "Abstract": "Dies ist ein Dummy-Abstract von CORE.",
        "DOI": "n/a",
        "Year": "2023",
        "Publisher": "n/a",
        "Population": "n/a",
        "FullData": {"demo_core": "CORE dummy data."}
    }]

##############################
# PDF/Download-Funktionen
##############################
def create_abstract_pdf(paper, output_file):
    """
    Erstellt ein PDF mit FPDF, in dem Titel + Abstract + Metadaten enthalten sind.
    """
    try:
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

        pdf.output(output_file)
        return True
    except Exception as e:
        st.error(f"Fehler beim Erstellen des PDF: {e}")
        return False

def _sanitize_filename(fname):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)

##############################
# Profil-Verwaltung
##############################
def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        if profile_name in profiles:
            return profiles[profile_name]
    return None

##############################
# Haupt-Modul
##############################
def module_codewords_pubmed():
    st.title("Codewörter & Multi-API-Suche: Abstract direkt in Liste + Paper Download")

    # 1) Profil-Auswahl
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte zuerst ein Profil speichern.")
        return
    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = load_settings(chosen_profile)
    st.subheader("Profil-Einstellungen")
    st.json(profile_data)

    # 2) Codewörter & Logik
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    # Button => Suche
    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        # APIs laut Profil
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

        if profile_data.get("use_core", False):
            st.write("### CORE")
            core_res = search_core(query_str, max_results=100)
            st.write(f"Anzahl CORE-Ergebnisse: {len(core_res)}")
            results_all.extend(core_res)

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
            return

        st.session_state["search_results"] = results_all

    # Anzeige / Filter
    if "search_results" in st.session_state and st.session_state["search_results"]:
        results_all = st.session_state["search_results"]
        st.write("## Gesamtergebnis (aus session_state)")

        df_main = pd.DataFrame([
            {
                "Title": p.get("Title", "n/a"),
                "PubMed ID": p.get("PubMed ID", "n/a"),
                "Year": p.get("Year", "n/a"),
                "Publisher": p.get("Publisher", "n/a"),
                "Population": p.get("Population", "n/a"),
                "Source": p.get("Source", "n/a"),
                "Abstract": p.get("Abstract", "n/a"),
            }
            for p in results_all
        ])

        adv_filter = st.checkbox("Erweiterte Filter-Funktion aktivieren?")

        if adv_filter:
            left_col, right_col = st.columns(2)
            with left_col:
                st.subheader("Originale Liste (ungefiltert)")
                st.dataframe(df_main)

            with right_col:
                st.subheader("Gefilterte Liste (rechts)")
                text_filter = st.text_input("Suchbegriff (Title/Publisher):", "")
                year_list = ["Alle"] + [str(y) for y in range(1900, 2026)]
                year_choice = st.selectbox("Erscheinungsjahr (1900-2025):", year_list)

                df_filtered = df_main.copy()
                if text_filter.strip():
                    tf = text_filter.lower()
                    def match_filter(row):
                        t = (row["Title"] or "").lower()
                        p = (row["Publisher"] or "").lower()
                        return (tf in t) or (tf in p)
                    df_filtered = df_filtered[df_filtered.apply(match_filter, axis=1)]

                if year_choice != "Alle":
                    df_filtered = df_filtered[df_filtered["Year"] == year_choice]

                st.dataframe(df_filtered)
        else:
            st.dataframe(df_main)

        # 1) Paper-Auswahl: per Multiselect
        st.subheader("Paper-Auswahl")
        # Du könntest ggf. einen Identifier konstruieren. Hier verwenden wir den 'Title' (kann Duplicate haben).
        # Besser: Title + Year oder Title + PMID
        df_main["identifier"] = df_main.apply(lambda r: f"{r['Title']}||{r['PubMed ID']}", axis=1)
        all_idents = df_main["identifier"].tolist()

        chosen_idents = st.multiselect("Wähle Paper (Basierend auf Titel/PMID):", all_idents)
        #  -> Set davon machen
        chosen_idents_set = set(chosen_idents)

        st.write("Ausgewählte Paper:")
        # Zeige sie an + Link in neuem Tab
        for c in chosen_idents:
            row = df_main.loc[df_main["identifier"] == c].iloc[0]
            # Du kannst zb einen Link bauen: st.markdown
            # Evtl. PubMed Link oder so:
            pmid = row["PubMed ID"]
            # Minimale Logik: wenn wir eine PMID haben, Link => https://pubmed.ncbi.nlm.nih.gov/{pmid}/
            # Sonst => "n/a"
            if pmid != "n/a":
                link_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
            else:
                link_url = "https://www.google.de"

            st.markdown(f"- **{row['Title']}** <br>"
                        f"[In neuem Tab öffnen]({link_url}){{:target=\"_blank\"}}",
                        unsafe_allow_html=True)

        # 2) Download-Button: wir machen PDFs nur für die ausgewählten Paper
        if st.button("Paper herunterladen & PDF erstellen"):
            if not chosen_idents:
                st.warning("Keine Paper ausgewählt.")
            else:
                # Baue Paper-Liste
                selected_papers = []
                for c in chosen_idents:
                    row = df_main.loc[df_main["identifier"] == c].iloc[0]
                    # Finde Original-Objekt in results_all
                    # (z. B. indem wir Title & PMID abgleichen)
                    match = None
                    for p in results_all:
                        if p["Title"] == row["Title"] and p["PubMed ID"] == row["PubMed ID"]:
                            match = p
                            break
                    if match:
                        selected_papers.append(match)

                if not selected_papers:
                    st.warning("Keine zu verarbeitenden Paper gefunden.")
                else:
                    # Lokales Verzeichnis / Pfad (im realen System)
                    out_dir = os.path.join(os.getcwd(), f"paper_download_{int(time.time())}")
                    if not os.path.exists(out_dir):
                        os.makedirs(out_dir)
                    st.write(f"Erstelle Ordner: `{out_dir}` (lokal)")

                    for i, paper in enumerate(selected_papers, start=1):
                        title_sane = _sanitize_filename(paper["Title"])[:60]
                        pdf_filename = f"{title_sane}.pdf"
                        pdf_path = os.path.join(out_dir, pdf_filename)
                        ok = create_abstract_pdf(paper, pdf_path)
                        if ok:
                            st.write(f"{i}. Abstract-PDF erstellt: **{pdf_filename}**")
                    st.success("Download/PDF-Erstellung abgeschlossen.")

        # 3) Excel-Export
        st.subheader("Excel-Export (alle Paper)")

        codewords_ = "Suchbegriffe"
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_codewords = codewords_.replace(" ", "_").replace(",", "_").replace("/", "_")
        filename = f"{safe_codewords}_{timestamp_str}.xlsx"

        df_main_excel = df_main[[
            "Title", "PubMed ID", "Abstract", "Year", "Publisher", "Population", "Source"
        ]]

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df_main_excel.to_excel(writer, sheet_name="Main", index=False)

            from collections import defaultdict
            source_groups = defaultdict(list)
            for p in results_all:
                src = p.get("Source", "n/a")
                source_groups[src].append(p)

            for s_name, plist in source_groups.items():
                rows = []
                for p in plist:
                    flat_fd = flatten_dict(p.get("FullData", {}))
                    flat_fd["Title"] = p.get("Title", "n/a")
                    flat_fd["PubMed ID"] = p.get("PubMed ID", "n/a")
                    flat_fd["Abstract"] = p.get("Abstract", "n/a")
                    flat_fd["Year"] = p.get("Year", "n/a")
                    flat_fd["Publisher"] = p.get("Publisher", "n/a")
                    flat_fd["Population"] = p.get("Population", "n/a")
                    flat_fd["Source"] = p.get("Source", "n/a")
                    rows.append(flat_fd)

                if rows:
                    df_api = pd.DataFrame(rows)
                else:
                    df_api = pd.DataFrame()

                short_sheet = s_name[:31] if s_name else "API"
                df_api.to_excel(writer, sheet_name=short_sheet, index=False)

        with open(filename, "rb") as f:
            st.download_button(
                "Excel-Datei herunterladen",
                data=f,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.info("Noch keine Suchergebnisse - bitte Suche starten.")


# Falls dieses Skript direkt gestartet wird:
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    module_codewords_pubmed()
