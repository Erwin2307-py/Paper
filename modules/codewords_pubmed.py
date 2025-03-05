import streamlit as st
import requests
import pandas as pd
import os
import time
import xml.etree.ElementTree as ET  # Für das Parsen des PubMed-XML

# --- Hier importieren wir 'scholarly' für die Google Scholar Suche ---
from scholarly import scholarly

##############################
# Echte API-Suchfunktionen
##############################

# 1) PubMed: ESearch (PMIDs holen)
def esearch_pubmed(query: str, max_results=100, timeout=10):
    """
    Führt eine PubMed-Suche via E-Utilities aus und gibt eine Liste von PMID zurück.
    """
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

# 2) PubMed: Helferfunktion zum Abruf der Abstracts (EFetch)
def fetch_pubmed_abstracts(pmids, timeout=10):
    """
    Ruft über EFetch die Abstracts zu einer Liste von PMID ab.
    Gibt ein Dict { pmid -> abstract_text } zurück.
    """
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

def parse_efetch_response(xml_text: str) -> dict:
    """
    Parst den XML-Text von EFetch und gibt ein Dict { pmid -> abstract } zurück.
    """
    root = ET.fromstring(xml_text)
    pmid_abstract_map = {}
    # Durchläuft alle <PubmedArticle>-Knoten
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid_val = pmid_el.text if pmid_el is not None else None
        # Achtung: es kann mehrere <AbstractText>-Elemente geben. Hier vereinfachen wir.
        abstract_el = article.find(".//AbstractText")
        abstract_text = abstract_el.text if abstract_el is not None else "n/a"
        if pmid_val:
            pmid_abstract_map[pmid_val] = abstract_text
    return pmid_abstract_map

# 3) PubMed: ESummary (Metadaten) + EFetch (Abstract) kombinieren
def get_pubmed_details(pmids: list):
    """
    Ruft über ESummary Details zu den übergebenen PMID ab und 
    via EFetch den echten Abstract. Gibt eine Liste Dictionaries zurück.
    Keys: [Source, Title, PubMed ID, DOI, Year, Abstract, Population].
    """
    if not pmids:
        return []

    # -- Erst ESummary für Titel, DOI, Jahr etc. --
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

    # -- Dann EFetch für die Abstracts --
    abstracts_map = fetch_pubmed_abstracts(pmids, timeout=10)

    results = []
    for pmid in pmids:
        info = data_summary.get("result", {}).get(pmid, {})
        pubdate = info.get("pubdate", "n/a")
        pubyear = pubdate[:4] if len(pubdate) >= 4 else "n/a"
        doi = info.get("elocationid", "n/a")
        title = info.get("title", "n/a")

        # Falls EFetch keinen Abstract liefert, nimm "n/a"
        abs_text = abstracts_map.get(pmid, "n/a")

        results.append({
            "Source": "PubMed",
            "Title": title,
            "PubMed ID": pmid,
            "DOI": doi,
            "Year": pubyear,
            "Abstract": abs_text,
            "Population": "n/a"
        })
    return results

def search_pubmed(query: str, max_results=100):
    """
    Führt die vollständige PubMed-Suche aus und ruft Details (inkl. Abstract) der gefundenen Paper ab.
    """
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

##############################
# Europe-PMC mit Timeout/Retry
##############################

def search_europe_pmc(query: str, max_results=100, timeout=30, retries=3, delay=5):
    """
    Führt eine Europe PMC-Suche aus und gibt eine Liste von Paper-Daten zurück.
    Hier mit höherem Timeout und Retry-Logik, um Read-Timeout-Fehler zu minimieren.
    """
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
                results.append({
                    "Source": "Europe PMC",
                    "Title": item.get("title", "n/a"),
                    "PubMed ID": item.get("pmid", "n/a"),
                    "DOI": item.get("doi", "n/a"),
                    "Year": str(item.get("pubYear", "n/a")),
                    "Abstract": item.get("abstractText", "n/a"),
                    "Population": "n/a"
                })
            return results

        except requests.exceptions.ReadTimeout:
            st.warning(f"Europe PMC: Read Timeout (Versuch {attempt+1}/{retries}). "
                       f"{delay}s warten und erneut versuchen...")
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
            # Bei anderen Fehlern nicht erneut versuchen
            return []

    st.error("Europe PMC-Suche wiederholt fehlgeschlagen (Timeout). Bitte später erneut versuchen.")
    return []

##############################
# Google Scholar
##############################

def search_google_scholar(query: str, max_results=100):
    """
    Führt eine Suche auf Google Scholar (inoffiziell via 'scholarly') durch
    und gibt eine Liste von Paper-Daten zurück (genau wie bei PubMed).
    """
    results = []
    try:
        # Suchergebnisse holen (Generator-Objekt)
        search_results = scholarly.search_pubs(query)

        # Wir holen maximal max_results Publikationen
        for _ in range(max_results):
            publication = next(search_results, None)
            if not publication:
                break

            bib = publication.get('bib', {})
            title = bib.get('title', 'n/a')
            authors = bib.get('author', 'n/a')
            pub_year = bib.get('pub_year', 'n/a')
            abstract = bib.get('abstract', 'n/a')

            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "PubMed ID": "n/a",
                "DOI": "n/a",
                "Year": str(pub_year),
                "Abstract": abstract,
                "Population": "n/a"
            })
    except Exception as e:
        st.error(f"Fehler bei der Google Scholar-Suche: {e}")
    return results

##############################
# Semantic Scholar
##############################

def search_semantic_scholar(query: str, max_results=100, retries=3, delay=5):
    """
    Führt eine Suche in der Semantic Scholar API durch und gibt eine Liste von Paper-Daten zurück.
    """
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
                    "Population": "n/a"
                })
            return results
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                st.warning(f"Rate limit bei Semantic Scholar erreicht, warte {delay} Sekunden und versuche es erneut...")
                time.sleep(delay)
                attempt += 1
                continue
            else:
                st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
                return []
        except Exception as e:
            st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
            return []
    st.error("Semantic Scholar: Rate limit überschritten. Bitte später erneut versuchen.")
    return []

##############################
# OpenAlex (Dummy)
##############################

def search_openalex(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für OpenAlex zurück.
    """
    return [{
        "Source": "OpenAlex",
        "Title": "Dummy Title from OpenAlex",
        "PubMed ID": "n/a",
        "DOI": "n/a",
        "Year": "2023",
        "Abstract": "Dies ist ein Dummy-Abstract von OpenAlex.",
        "Population": "n/a"
    }]

##############################
# CORE (Dummy)
##############################

def search_core(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für CORE zurück.
    """
    return [{
        "Source": "CORE",
        "Title": "Dummy Title from CORE",
        "PubMed ID": "n/a",
        "DOI": "n/a",
        "Year": "2023",
        "Abstract": "Dies ist ein Dummy-Abstract von CORE.",
        "Population": "n/a"
    }]

##############################
# Profil-Verwaltung
##############################

def load_settings(profile_name: str):
    """
    Lädt Einstellungen aus st.session_state["profiles"][profile_name].
    """
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

    # 1) Dropdown: Profile auswählen
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

    # 2) Eingabefeld für Codewörter und Logik
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    # 3) Suchanfrage zusammenbauen und API-Suche starten
    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        # Codewörter mit AND/OR verknüpfen
        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        # Aktivierte APIs laut Profil
        if profile_data.get("use_pubmed", False):
            st.write("### PubMed")
            res = search_pubmed(query_str, max_results=100)
            st.write(f"Anzahl PubMed-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_epmc", False):
            st.write("### Europe PMC")
            res = search_europe_pmc(query_str, max_results=100)
            st.write(f"Anzahl Europe PMC-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_google", False):
            st.write("### Google Scholar")
            res = search_google_scholar(query_str, max_results=100)
            st.write(f"Anzahl Google Scholar-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_semantic", False):
            st.write("### Semantic Scholar")
            res = search_semantic_scholar(query_str, max_results=100)
            st.write(f"Anzahl Semantic Scholar-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_openalex", False):
            st.write("### OpenAlex")
            res = search_openalex(query_str, max_results=100)
            st.write(f"Anzahl OpenAlex-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_core", False):
            st.write("### CORE")
            res = search_core(query_str, max_results=100)
            st.write(f"Anzahl CORE-Ergebnisse: {len(res)}")
            results_all.extend(res)

        # 4) Ergebnisse ausgeben
        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
        else:
            st.write("## Gesamtergebnis aus allen aktivierten APIs")
            
            # (a) Tabelle mit allen Ergebnissen anzeigen
            df = pd.DataFrame(results_all)
            st.dataframe(df)

            # (b) Für jedes Paper einen Expander mit Abstract & Metadaten
            st.write("### Klicke auf einen Titel, um das Abstract anzuzeigen:")
            for idx, row in df.iterrows():
                with st.expander(f"{row['Title']} (Quelle: {row['Source']})"):
                    st.write(f"**PubMed ID**: {row['PubMed ID']}")
                    st.write(f"**DOI**: {row['DOI']}")
                    st.write(f"**Jahr**: {row['Year']}")
                    st.write(f"**Population**: {row['Population']}")
                    st.markdown("---")
                    st.write(f"**Abstract**:\n\n{row['Abstract']}")

    st.write("---")
    st.info("Dieses Modul nutzt das ausgewählte Profil, um Codewörter (mit AND/OR-Verknüpfung) "
            "auf alle aktivierten APIs anzuwenden und gibt alle Paper-Informationen aus (Quelle, "
            "Titel, PubMed ID, DOI, Jahr, Abstract, Population).")

# Falls dieses Modul als Hauptskript ausgeführt wird:
if __name__ == "__main__":
    module_codewords_pubmed()
