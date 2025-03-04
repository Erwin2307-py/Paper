# modules/online_api_filter.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO


###############################################################################
# 1) Hilfsfunktionen für PubMed
###############################################################################

def check_pubmed_connection():
    """
    Beispiel: Prüft Verbindung zu PubMed (vereinfacht).
    """
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def search_pubmed_simple(query="test", limit=10):
    """
    Beispiel: Sucht bis zu 'limit' PubMed-Einträge nach dem Query.
    Gibt das JSON-Dict zurück oder None, wenn etwas schiefgeht.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


###############################################################################
# 2) Hilfsfunktionen für Europe PMC
###############################################################################

def check_europe_pmc_connection():
    """
    Beispiel: Prüft Verbindung zu Europe PMC (vereinfacht).
    """
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 1}
    try:
        r = requests.get(test_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

def search_europe_pmc_simple(query="test", limit=10):
    """
    Beispiel: Sucht bis zu 'limit' Europe PMC-Einträge nach dem Query.
    Gibt das JSON-Dict zurück oder None, wenn etwas schiefgeht.
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": limit
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


###############################################################################
# 3) HAUPTFUNKTION: Wird im Hauptmenü aufgerufen
###############################################################################

def module_online_api_filter():
    """
    Diese Funktion wird aus main_app.py heraus aufgerufen,
    z.B. via: from modules.online_api_filter import module_online_api_filter
              ...
              module_online_api_filter()
    """
    st.title("Online-API_Filter: PubMed & Europe PMC")

    st.markdown("Wähle hier die APIs und starte eine einfache Suche.")

    # --- Auswahl der APIs per Checkbox ---
    col_api1, col_api2 = st.columns(2)
    with col_api1:
        use_pubmed = st.checkbox("PubMed", value=True)
    with col_api2:
        use_epmc = st.checkbox("Europe PMC", value=True)

    # --- Textfeld für Query & Button ---
    query = st.text_input("Suchbegriff:", "test")
    limit = st.number_input("Max. Ergebnisse pro API", min_value=1, max_value=100, value=10, step=1)

    if st.button("Suche starten"):
        # Liste zum Sammeln der Ergebnisse
        results = []

        # PubMed-Suche
        if use_pubmed:
            pubmed_data = search_pubmed_simple(query, limit=limit)
            if pubmed_data:
                results.append(("PubMed", pubmed_data))
            else:
                st.warning("Keine Daten oder Fehler bei PubMed.")

        # Europe PMC-Suche
        if use_epmc:
            epmc_data = search_europe_pmc_simple(query, limit=limit)
            if epmc_data:
                results.append(("Europe PMC", epmc_data))
            else:
                st.warning("Keine Daten oder Fehler bei Europe PMC.")

        # Ergebnisse ausgeben
        if not results:
            st.info("Keine APIs gewählt oder keine Daten.")
        else:
            for (api_name, api_data) in results:
                st.subheader(f"Ergebnisse von {api_name}")
                st.json(api_data)

    st.write("---")

    # Optional: Verbindungstests einzeln
    st.markdown("### (Optional) Verbindungstests")
    col_test1, col_test2 = st.columns(2)
    with col_test1:
        if st.button("Check PubMed-Verbindung"):
            if check_pubmed_connection():
                st.success("PubMed: Verbindung OK")
            else:
                st.error("PubMed: Verbindung fehlgeschlagen!")
    with col_test2:
        if st.button("Check Europe PMC-Verbindung"):
            if check_europe_pmc_connection():
                st.success("Europe PMC: Verbindung OK")
            else:
                st.error("Europe PMC: Verbindung fehlgeschlagen!")

    st.write("Füge weitere APIs, Filteroptionen etc. nach Bedarf hinzu.")
