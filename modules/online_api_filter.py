# modules/online_api_filter.py

import streamlit as st
import requests

##############################################################################
# 1) Verbindungstest-Funktionen
##############################################################################

def check_pubmed_connection():
    """
    Beispiel: Prüft Verbindung zu PubMed (vereinfacht).
    """
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def check_europe_pmc_connection():
    """
    Beispiel: Prüft Verbindung zu Europe PMC (vereinfacht).
    """
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 1}
    try:
        r = requests.get(test_url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

##############################################################################
# 2) Hauptfunktion (wird vom Hauptmenü aufgerufen)
##############################################################################

def module_online_api_filter():
    """
    Diese Funktion zeigt dem Nutzer zwei Checkboxen (PubMed/Europe PMC).
    Danach kann er per Button die Verbindung testen – pro angekreuzter API
    wird ein grüner oder roter Punkt angezeigt.
    """
    st.title("API-Auswahl & Verbindungstest (ohne Suchabfrage)")

    # Checkboxen für die beiden APIs
    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=True)
    with col2:
        use_epmc = st.checkbox("Europe PMC", value=True)

    # Button für Verbindungstest
    if st.button("Verbindung prüfen"):
        st.write("**Ergebnis:**")
        
        # Kurze Hilfsfunktionen für grüne / rote Punkte
        def green_dot():
            return "<span style='color: limegreen; font-size: 25px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 25px;'>&#9679;</span>"

        # Prüfen, was ausgewählt wurde, und Verbindung testen
        if not use_pubmed and not use_epmc:
            st.info("Keine API ausgewählt. Bitte mindestens eine ankreuzen.")
            return

        # PubMed
        if use_pubmed:
            ok = check_pubmed_connection()
            if ok:
                st.markdown(f"{green_dot()} **PubMed**: Verbindung OK", unsafe_allow_html=True)
            else:
                st.markdown(f"{red_dot()} **PubMed**: Verbindung fehlgeschlagen!", unsafe_allow_html=True)

        # Europe PMC
        if use_epmc:
            ok = check_europe_pmc_connection()
            if ok:
                st.markdown(f"{green_dot()} **Europe PMC**: Verbindung OK", unsafe_allow_html=True)
            else:
                st.markdown(f"{red_dot()} **Europe PMC**: Verbindung fehlgeschlagen!", unsafe_allow_html=True)
    else:
        st.write("Hier kannst du eine oder beide APIs anklicken und dann auf 'Verbindung prüfen' drücken.")
