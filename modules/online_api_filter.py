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

def search_pubmed_simple(query="test"):
    """
    Beispiel: Sucht bis zu 10 PubMed-Einträge nach dem Query.
    Gibt das JSON-Dict zurück oder None, wenn etwas schiefgeht.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 10}
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
        # Minimal-Kriterium: "resultList" in data und "result" in data["resultList"]
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
        "pageSize": limit  # bis zu 'limit' Ergebnisse
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
    st.title("Online-API_Filter (Kombiniert)")

    st.markdown("Diese Seite kommt aus `modules/online_api_filter.py`.")
    st.write("Hier kannst du deine API-Auswahl, Filter-UI etc. integrieren.")

    ############################################################################
    # A) Verbindungstests
    ############################################################################
    st.subheader("Verbindungstests")

    col1, col2 = st.columns(2)
    with col1:
        # Button: Prüfe PubMed-Verbindung
        if st.button("Check PubMed-Verbindung"):
            if check_pubmed_connection():
                st.success("PubMed: Verbindung OK")
            else:
                st.error("PubMed: Verbindung fehlgeschlagen!")

    with col2:
        # Button: Prüfe Europe PMC-Verbindung
        if st.button("Check Europe PMC-Verbindung"):
            if check_europe_pmc_connection():
                st.success("Europe PMC: Verbindung OK")
            else:
                st.error("Europe PMC: Verbindung fehlgeschlagen!")

    ############################################################################
    # B) Einfache Suchen (PubMed und Europe PMC)
    ############################################################################
    st.subheader("Einfache Suchen")
    query = st.text_input("Suchbegriff (z.B. 'cancer'):", "test")

    col_a, col_b = st.columns(2)

    with col_a:
        st.write("**PubMed-Suche**")
        if st.button("Starte einfache PubMed-Suche"):
            pubmed_data = search_pubmed_simple(query)
            if pubmed_data:
                st.write("PubMed-Ergebnisse (raw JSON):")
                st.json(pubmed_data)
            else:
                st.warning("Keine Daten oder Fehler bei PubMed.")

    with col_b:
        st.write("**Europe PMC-Suche**")
        if st.button("Starte einfache Europe PMC-Suche"):
            epmc_data = search_europe_pmc_simple(query, limit=10)
            if epmc_data:
                st.write("Europe PMC-Ergebnisse (raw JSON):")
                st.json(epmc_data)
            else:
                st.warning("Keine Daten oder Fehler bei Europe PMC.")

    st.write("---")
    st.write("Hier könntest du weitere Filter- und Auswertungs-Logik hinzufügen (z.B. Excel-Export, Abstract-Analyse etc.).")
