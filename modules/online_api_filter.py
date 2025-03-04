# modules/online_api_filter.py

import streamlit as st
import requests

##############################################################################
# 1) Verbindungstest-Funktionen
##############################################################################

def check_pubmed_connection(timeout=5):
    """
    Prüft Verbindung zu PubMed (vereinfacht).
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

def check_europe_pmc_connection(timeout=5):
    """
    Prüft Verbindung zu Europe PMC (vereinfacht).
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

def check_google_scholar_connection(timeout=5):
    """
    Prüft Verbindung zu Google Scholar, indem eine kleine Testsuche durchgeführt wird.
    Erfordert, dass das Paket 'scholarly' installiert ist.
    """
    try:
        from scholarly import scholarly
        # Suche nach 'test' und rufe 1 Ergebnis ab
        search_results = scholarly.search_pubs("test")
        _ = next(search_results)  # Wenn das klappt, scheint Verbindung zu gehen
        return True
    except Exception:
        return False

def check_semantic_scholar_connection(timeout=5):
    """
    Prüft Verbindung zu Semantic Scholar (API).
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": "test", "limit": 1, "fields": "title"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        # Einfaches Kriterium: 'data' im JSON
        return "data" in data
    except Exception:
        return False

##############################################################################
# 2) Hauptfunktion: Wird vom Hauptmenü aufgerufen
##############################################################################

def module_online_api_filter():
    """
    Diese Funktion zeigt dem Nutzer vier Checkboxen (PubMed/Europe PMC/Google Scholar/Semantic Scholar).
    Danach kann er per Button die Verbindung prüfen – pro angekreuzter API
    wird ein grüner oder roter Punkt inline ausgegeben.
    """
    st.title("API-Auswahl & Verbindungstest")

    st.write("Aktiviere die gewünschten APIs und klicke auf 'Verbindung prüfen'.")

    # Checkboxen für die vier APIs
    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=True)
        use_google = st.checkbox("Google Scholar", value=False)
    with col2:
        use_epmc = st.checkbox("Europe PMC", value=True)
        use_semantic = st.checkbox("Semantic Scholar", value=False)

    # Button für Verbindungstest
    if st.button("Verbindung prüfen"):
        # Hilfsfunktionen für grüne / rote Punkte
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"

        # Liste für die einzelnen API-Ergebnisse
        dots_list = []

        # PubMed
        if use_pubmed:
            ok = check_pubmed_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>PubMed</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>PubMed</strong>: FAIL")

        # Europe PMC
        if use_epmc:
            ok = check_europe_pmc_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>Europe PMC</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Europe PMC</strong>: FAIL")

        # Google Scholar
        if use_google:
            ok = check_google_scholar_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>Google Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Google Scholar</strong>: FAIL")

        # Semantic Scholar
        if use_semantic:
            ok = check_semantic_scholar_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>Semantic Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Semantic Scholar</strong>: FAIL")

        # Falls keine API ausgewählt
        if not dots_list:
            st.info("Keine API ausgewählt. Bitte mindestens eine ankreuzen.")
        else:
            # Ausgabe in einer Zeile nebeneinander
            # mit etwas Abstand: &nbsp; = non-breaking space
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)
    else:
        st.write("Bitte wähle mindestens eine API aus und klicke auf 'Verbindung prüfen'.")
