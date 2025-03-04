# modules/online_api_filter.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

###############################################################################
# Optionale Hilfsfunktionen, falls du sie in diesem Modul brauchst:
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
# Hauptfunktion, die vom Hauptmenü aufgerufen wird:
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

    # Beispiel: Button und Test-Funktion
    if st.button("Check PubMed-Verbindung"):
        if check_pubmed_connection():
            st.success("PubMed: Verbindung OK")
        else:
            st.error("PubMed: Verbindung fehlgeschlagen!")

    # Beispiel: einfache Suche
    query = st.text_input("Suchbegriff für PubMed:", "test")
    if st.button("Starte einfache PubMed-Suche"):
        data = search_pubmed_simple(query)
        if data:
            st.write("PubMed-Daten als JSON:")
            st.json(data)
        else:
            st.warning("Keine Daten oder Fehler aufgetreten.")
    
    st.write("Füge hier beliebige weitere APIs, Filteroptionen etc. hinzu.")
