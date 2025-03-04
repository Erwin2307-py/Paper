# file: codewords_pubmed.py

import streamlit as st
import requests

##############################
# Dummy Suchfunktionen für verschiedene APIs
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
    (Hinweis: Abstract und Populationsgröße werden hier als Demo nicht detailliert abgerufen.)
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
                "source": "PubMed",
                "title": info.get("title", "n/a"),
                "pubmed_id": pmid,
                "doi": info.get("elocationid", "n/a"),
                "year": info.get("pubdate", "n/a")[:4] if info.get("pubdate") else "n/a",
                "abstract": "Abstract nicht abgerufen",  # Für Demo
                "pop_size": "n/a"  # Für Demo
            })
        return results
    except Exception as e:
        st.error(f"Fehler beim Abrufen von PubMed-Daten: {e}")
        return []

def search_pubmed(query: str, max_results=100):
    """
    Sucht in PubMed und ruft Details zu den gefundenen Papern ab.
    """
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

def search_europe_pmc(query: str, max_results=100):
    """
    Führt eine Europe PMC-Suche aus und gibt Dummy-Daten zurück.
    (Echte Detailabfragen müssten analog zu PubMed implementiert werden.)
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
                "source": "Europe PMC",
                "title": item.get("title", "n/a"),
                "pubmed_id": item.get("pmid", "n/a"),
                "doi": item.get("doi", "n/a"),
                "year": str(item.get("pubYear", "n/a")),
                "abstract": item.get("abstractText", "n/a"),
                "pop_size": "n/a"  # Für Demo
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
        "source": "Google Scholar",
        "title": "Dummy Title from Google Scholar",
        "pubmed_id": "n/a",
        "doi": "n/a",
        "year": "2023",
        "abstract": "Dies ist ein Dummy-Abstract.",
        "pop_size": "n/a"
    }]

def search_semantic_scholar(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für Semantic Scholar zurück.
    """
    return [{
        "source": "Semantic Scholar",
        "title": "Dummy Title from Semantic Scholar",
        "pubmed_id": "n/a",
        "doi": "n/a",
        "year": "2023",
        "abstract": "Dies ist ein Dummy-Abstract.",
        "pop_size": "n/a"
    }]

def search_openalex(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für OpenAlex zurück.
    """
    return [{
        "source": "OpenAlex",
        "title": "Dummy Title from OpenAlex",
        "pubmed_id": "n/a",
        "doi": "n/a",
        "year": "2023",
        "abstract": "Dies ist ein Dummy-Abstract.",
        "pop_size": "n/a"
    }]

def search_core(query: str, max_results=100):
    """
    Dummy-Funktion: Gibt Beispiel-Daten für CORE zurück.
    """
    return [{
        "source": "CORE",
        "title": "Dummy Title from CORE",
        "pubmed_id": "n/a",
        "doi": "n/a",
        "year": "2023",
        "abstract": "Dies ist ein Dummy-Abstract.",
        "pop_size": "n/a"
    }]

##############################
# Profil-Verwaltung (aus st.session_state)
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
# Haupt-Modul: Codewörter & API-Suche
##############################

def module_codewords_pubmed():
    st.title("Codewörter & Multi-API-Suche (mind. 100 Paper pro API)")

    # 1) Profile auswählen (Dropdown)
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte erst ein Profil in einem anderen Modul speichern.")
        return

    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = load_settings(chosen_profile)
    st.subheader("Profil-Einstellungen")
    st.json(profile_data)

    # 2) Codewörter und Logik abfragen
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    # 3) Suchanfrage zusammenbauen
    if st.button("Suche starten"):
        # Codewörter parsen
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Suchanfrage:", query_str)

        results_all = []

        # 4) Suche in allen aktivierten APIs (aus dem Profil)
        if profile_data.get("use_pubmed", False):
            st.write("### PubMed")
            res = search_pubmed(query_str, max_results=100)
            st.write(f"Anzahl PubMed: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if profile_data.get("use_epmc", False):
            st.write("### Europe PMC")
            res = search_europe_pmc(query_str, max_results=100)
            st.write(f"Anzahl Europe PMC: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if profile_data.get("use_google", False):
            st.write("### Google Scholar")
            res = search_google_scholar(query_str, max_results=100)
            st.write(f"Anzahl Google Scholar: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if profile_data.get("use_semantic", False):
            st.write("### Semantic Scholar")
            res = search_semantic_scholar(query_str, max_results=100)
            st.write(f"Anzahl Semantic Scholar: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if profile_data.get("use_openalex", False):
            st.write("### OpenAlex")
            res = search_openalex(query_str, max_results=100)
            st.write(f"Anzahl OpenAlex: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if profile_data.get("use_core", False):
            st.write("### CORE")
            res = search_core(query_str, max_results=100)
            st.write(f"Anzahl CORE: {len(res)}")
            results_all.extend(res)
            st.write(res)

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
        else:
            st.write("## Gesamtergebnis aus allen aktivierten APIs")
            st.write(results_all)

    st.write("---")
    st.info("Dieses Modul nutzt das ausgewählte Profil, um die Codewörter (mit AND/OR-Verknüpfung) auf alle aktivierten APIs anzuwenden und gibt alle Paper-Informationen aus (Quelle, Titel, PubMed ID, DOI, Jahr, Abstract, Population).")
