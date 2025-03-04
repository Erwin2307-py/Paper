# modules/online_api_filter.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

###############################################################################
# 1) CHECK-Funktionen (Verbindungstests)
###############################################################################

def check_pubmed_connection(timeout=10):
    """
    Beispiel: Prüft, ob PubMed erreichbar ist.
    """
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def check_europe_pmc_connection(timeout=10):
    """
    Beispiel: Prüft, ob Europe PMC erreichbar ist.
    """
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 1}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

def check_core_connection(api_key="", timeout=15):
    """
    Beispiel: Prüft, ob CORE erreichbar ist.
    (Benötigt einen CORE-API-Key)
    """
    if not api_key:
        return False

    # Minimaler Test-Call
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"q": "test", "limit": 1}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "results" in data
    except Exception:
        return False

###############################################################################
# 2) SEARCH-Funktionen (Suche in den jeweiligen APIs)
###############################################################################

def search_pubmed_simple(query="test"):
    """
    Beispiel: Sucht bis zu 10 PubMed-Einträge nach dem Query.
    Gibt JSON-Daten (dict) zurück oder None bei Fehler.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 10}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def search_europe_pmc_simple(query="test"):
    """
    Beispiel: Sucht bis zu 10 Europe PMC-Einträge nach dem Query.
    Hier limitieren wir mal auf 10 zur Demo.
    Gibt JSON-Daten (dict) zurück oder None bei Fehler.
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 10}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def search_core_simple(query="test", api_key="", limit=10):
    """
    Beispiel: Sucht bis zu `limit` CORE-Einträge nach dem Query.
    Benötigt CORE-API-Key.
    Gibt JSON-Daten (dict) zurück oder None bei Fehler.
    """
    if not api_key:
        return None
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"q": query, "limit": limit}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
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
    st.write("Hier kannst du API-Verbindungen testen und einfache Suchen ausführen.")

    ############################################################################
    # A) Verbindungstest (Buttons)
    ############################################################################
    st.subheader("Verbindungstests")

    col1, col2, col3 = st.columns(3)

    # PubMed
    with col1:
        if st.button("Check PubMed-Verbindung"):
            if check_pubmed_connection():
                st.success("PubMed: Verbindung OK")
            else:
                st.error("PubMed: Verbindung fehlgeschlagen!")

    # Europe PMC
    with col2:
        if st.button("Check Europe PMC-Verbindung"):
            if check_europe_pmc_connection():
                st.success("Europe PMC: Verbindung OK")
            else:
                st.error("Europe PMC: Verbindung fehlgeschlagen!")

    # CORE
    with col3:
        # Für CORE kannst du deinen API-Key in st.secrets lagern
        core_api_key = st.secrets.get("CORE_API_KEY", "")
        if st.button("Check CORE-Verbindung"):
            if check_core_connection(core_api_key):
                st.success("CORE: Verbindung OK")
            else:
                st.error("CORE: Verbindung fehlgeschlagen (Key nötig?)")

    ############################################################################
    # B) Einfache Suche
    ############################################################################
    st.subheader("Einfache Suchen")

    query = st.text_input("Suchbegriff (z.B. 'cancer'):", "test")

    col_a, col_b, col_c = st.columns(3)
    # Suche PubMed
    with col_a:
        if st.button("PubMed-Suche starten"):
            result = search_pubmed_simple(query)
            if result:
                st.write("PubMed-Ergebnisse (raw JSON):")
                st.json(result)
            else:
                st.warning("Keine Daten oder Fehler bei PubMed.")

    # Suche Europe PMC
    with col_b:
        if st.button("Europe PMC-Suche starten"):
            result = search_europe_pmc_simple(query)
            if result:
                st.write("Europe PMC-Ergebnisse (raw JSON):")
                st.json(result)
            else:
                st.warning("Keine Daten oder Fehler bei Europe PMC.")

    # Suche CORE
    with col_c:
        core_api_key = st.secrets.get("CORE_API_KEY", "")
        if st.button("CORE-Suche starten"):
            result = search_core_simple(query, api_key=core_api_key, limit=10)
            if result:
                st.write("CORE-Ergebnisse (raw JSON):")
                st.json(result)
            else:
                st.warning("Keine Daten oder Fehler bei CORE (API-Key nötig).")

    st.write("---")
    st.write("Hier könntest du weitere Filter- und Auswertungs-Logik anfügen, z. B. ")
    st.markdown("- Keyword-Filter (Checkboxen)  
                 - Anzeigen von Abstracts  
                 - Export in Excel  
                 - usw.")

