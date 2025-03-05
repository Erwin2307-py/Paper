import streamlit as st
import requests
import pandas as pd
import os
import time
import xml.etree.ElementTree as ET
from scholarly import scholarly
from datetime import datetime
from collections import defaultdict

##############################
# Dict-Flattening-Funktion
##############################

def flatten_dict(d, parent_key="", sep="__"):
    """
    Macht aus verschachtelten Dicts eine flache Key->Value-Struktur.
    Bsp.: {"a": 1, "b": {"x": 10, "y": 20}} 
    => {"a": 1, "b__x": 10, "b__y": 20}
    """
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

        full_data = dict(info)  # ESummary Original
        full_data["abstract"] = abs_text  # EFetch-Abstract

        results.append({
            "Source": "PubMed",
            "Title": title,
            "PubMed ID": pmid,
            "DOI": doi,
            "Year": pubyear,
            "Abstract": abs_text,
            "Population": "n/a",
            "Publisher": publisher,
            "FullData": full_data
        })
    return results

def search_pubmed(query: str, max_results=100):
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

##############################
# Europe PMC (Timeout/Retry)
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
                # Versuch "journalInfo"->"journal" als Publisher 
                publisher = "n/a"
                jinfo = item.get("journalInfo", {})
                if isinstance(jinfo, dict):
                    publisher = jinfo.get("journal", "n/a")

                results.append({
                    "Source": "Europe PMC",
                    "Title": item.get("title", "n/a"),
                    "PubMed ID": item.get("pmid", "n/a"),
                    "DOI": item.get("doi", "n/a"),
                    "Year": str(item.get("pubYear", "n/a")),
                    "Abstract": item.get("abstractText", "n/a"),
                    "Population": "n/a",
                    "Publisher": publisher,
                    "FullData": dict(item)  # Rohdaten
                })
            return results
        except requests.exceptions.ReadTimeout:
            st.warning(f"Europe PMC: Read Timeout (Versuch {attempt+1}/{retries}). "
                       f"{delay}s warten und erneut versuchen...")
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
                "DOI": "n/a",
                "Year": str(pub_year),
                "Abstract": abstract,
                "Population": "n/a",
                "Publisher": "n/a",
                "FullData": dict(publication)  # Alles von "scholarly"
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
    while attempt < retries:
        try:
            r = requests.get(base_url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            papers = data.get("data", [])
            results = []
            for paper in papers:
                results.append({
                    "Source": "Semantic Scholar",
                    "Title": paper.get("title", "n/a"),
                    "PubMed ID": "n/a",
                    "DOI": "n/a",
                    "Year": str(paper.get("year", "n/a")),
                    "Abstract": paper.get("abstract", "n/a"),
                    "Population": "n/a",
                    "Publisher": "n/a",
                    "FullData": dict(paper)
                })
            return results
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                st.warning(f"Rate limit bei Semantic Scholar erreicht, warte {delay} Sekunden...")
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
    return []

##############################
# OpenAlex / CORE (Dummies)
##############################

def search_openalex(query: str, max_results=100):
    return [{
        "Source": "OpenAlex",
        "Title": "Dummy Title from OpenAlex",
        "PubMed ID": "n/a",
        "DOI": "n/a",
        "Year": "2023",
        "Abstract": "Dies ist ein Dummy-Abstract von OpenAlex.",
        "Population": "n/a",
        "Publisher": "n/a",
        "FullData": {"demo_openalex": "Hier stünden Originaldaten."}
    }]

def search_core(query: str, max_results=100):
    return [{
        "Source": "CORE",
        "Title": "Dummy Title from CORE",
        "PubMed ID": "n/a",
        "DOI": "n/a",
        "Year": "2023",
        "Abstract": "Dies ist ein Dummy-Abstract von CORE.",
        "Population": "n/a",
        "Publisher": "n/a",
        "FullData": {"demo_core": "CORE dummy data."}
    }]

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
    st.title("Codewörter & Multi-API-Suche (mind. 100 Paper pro API)")

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

    # 2) Codewörter + Logik
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    # 3) Suche
    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        # APIs laut Profil abfragen
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

        st.write("## Gesamtergebnis aus allen aktivierten APIs")

        # (A) MAIN-Sheet: Grundlegende Felder
        df_main = pd.DataFrame([
            {
                "Title": p.get("Title", "n/a"),
                "PubMed ID": p.get("PubMed ID", "n/a"),
                "Abstract": p.get("Abstract", "n/a"),
                "Year": p.get("Year", "n/a"),
                "Publisher": p.get("Publisher", "n/a"),
                "Population": p.get("Population", "n/a"),
                "Source": p.get("Source", "n/a"),
            }
            for p in results_all
        ])

        # Zeige Main-Sheet in Streamlit
        st.dataframe(df_main)

        # Expander für Abstract
        st.write("### Klicke auf einen Titel, um das Abstract anzuzeigen:")
        for idx, row in df_main.iterrows():
            with st.expander(f"{row['Title']} (Quelle: {row['Source']})"):
                st.write(f"**PubMed ID**: {row.get('PubMed ID', 'n/a')}")
                st.write(f"**Jahr**: {row.get('Year', 'n/a')}")
                st.write(f"**Publisher**: {row.get('Publisher', 'n/a')}")
                st.write(f"**Population**: {row.get('Population', 'n/a')}")
                st.markdown("---")
                st.write(f"**Abstract**:\n\n{row.get('Abstract', 'n/a')}")

        # (B) Erzeuge "pro API ein eigenes Tabellenblatt" und flatten "FullData"
        from openpyxl import Workbook  # nur um sicherzugehen, dass wir openpyxl haben
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Codewörter "säubern" für Dateinamen
        safe_codewords = codewords_str.strip().replace(" ", "_").replace(",", "_").replace("/", "_")
        filename = f"{safe_codewords}_{timestamp_str}.xlsx"

        # 1) Groups nach Source
        from collections import defaultdict
        source_groups = defaultdict(list)
        for p in results_all:
            src = p.get("Source", "n/a")
            source_groups[src].append(p)

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            # Sheet "Main"
            df_main.to_excel(writer, sheet_name="Main", index=False)

            # Jetzt pro API ein Sheet
            for source_name, papers_list in source_groups.items():
                # flatten each paper's FullData
                rows = []
                for paper in papers_list:
                    fd = paper.get("FullData", {})
                    flattened = flatten_dict(fd)  # => dict mit Key->Value
                    # Zusätzliche Standardfelder
                    flattened["Title"] = paper.get("Title", "n/a")
                    flattened["PubMed ID"] = paper.get("PubMed ID", "n/a")
                    flattened["Year"] = paper.get("Year", "n/a")
                    flattened["Publisher"] = paper.get("Publisher", "n/a")
                    flattened["Population"] = paper.get("Population", "n/a")
                    flattened["Source"] = paper.get("Source", "n/a")

                    rows.append(flattened)

                if rows:
                    df_api = pd.DataFrame(rows)
                else:
                    df_api = pd.DataFrame()  # leer

                # Sheet-Name (max 31 Zeichen)
                short_name = source_name[:31] if source_name else "API"
                df_api.to_excel(writer, sheet_name=short_name, index=False)

        st.success(f"Excel-Datei mit 'Main' + pro API ein Sheet erstellt: {filename}")

        # Download-Button
        with open(filename, "rb") as f:
            st.download_button(
                label="Excel-Datei herunterladen",
                data=f,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.write("---")
    st.info("Dieses Modul sucht in allen aktivierten APIs und erzeugt ein Excel mit einem Main-Sheet "
            "sowie je einem Sheet pro API. Dort sind alle Felder in eigenen Spalten (geflattete 'FullData').")


# Falls dieses Modul als Hauptskript ausgeführt wird:
if __name__ == "__main__":
    module_codewords_pubmed()
