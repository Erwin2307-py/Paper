import streamlit as st
import requests
import pandas as pd
import os

##############################
# Echte API-Suchfunktionen
##############################

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

def get_pubmed_details(pmids: list):
    """
    Ruft über ESummary Details zu den übergebenen PMID ab und gibt eine Liste von Dictionaries zurück.
    Liefert Informationen wie Quelle, Titel, PubMed ID, DOI, Jahr, Abstract und Population.
    (Hinweis: Für Abstract und Populationsgröße werden Demo-Werte zurückgegeben.)
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for pmid in pmids:
            info = data.get("result", {}).get(pmid, {})
            results.append({
                "Source": "PubMed",
                "Title": info.get("title", "n/a"),
                "PubMed ID": pmid,
                "DOI": info.get("elocationid", "n/a"),
                "Year": info.get("pubdate", "n/a")[:4] if info.get("pubdate") else "n/a",
                "Abstract": "Abstract nicht abgerufen",  # Hier könnte man via efetch nachladen
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Fehler beim Abrufen von PubMed-Daten: {e}")
        return []

def search_pubmed(query: str, max_results=100):
    """
    Führt die vollständige PubMed-Suche aus und ruft Details der gefundenen Paper ab.
    """
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

def search_europe_pmc(query: str, max_results=100):
    """
    Führt eine Europe PMC-Suche aus und gibt eine Liste von Paper-Daten zurück.
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results
    }
    try:
        r = requests.get(url, params=params, timeout=10)
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
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return []

def search_google_scholar(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für Google Scholar zurück.
    """
    return [{
        "Source": "Google Scholar",
        "Title": "Dummy Title from Google Scholar",
        "PubMed ID": "n/a",
        "DOI": "n/a",
        "Year": "2023",
        "Abstract": "Dies ist ein Dummy-Abstract von Google Scholar.",
        "Population": "n/a"
    }]

def search_semantic_scholar(query: str, max_results=100):
    """
    Führt eine Suche in der Semantic Scholar API durch und gibt eine Liste von Paper-Daten zurück.
    Die Ergebnisse werden in das von Codewords erwartete Format transformiert.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,abstract"
    }
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
                "PubMed ID": "n/a",  # Semantic Scholar liefert in der Regel keine PubMed ID
                "DOI": "n/a",        # DOI ist hier nicht direkt verfügbar
                "Year": str(paper.get("year", "n/a")),
                "Abstract": paper.get("abstract", "n/a"),
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
        return []

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
# Profil-Verwaltung: Laden der Einstellungen aus st.session_state
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
# Haupt-Modul: Codewörter & Multi-API-Suche
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

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
        else:
            st.write("## Gesamtergebnis aus allen aktivierten APIs")
            df = pd.DataFrame(results_all)
            st.dataframe(df)  # Schöne tabellarische Darstellung

    st.write("---")
    st.info("Dieses Modul nutzt das ausgewählte Profil, um Codewörter (mit AND/OR-Verknüpfung) auf alle aktivierten APIs anzuwenden und gibt alle Paper-Informationen aus (Quelle, Titel, PubMed ID, DOI, Jahr, Abstract, Population).")
