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
    Prüft Verbindung zu Google Scholar, indem eine kurze Testsuche durchgeführt wird.
    Erfordert, dass 'scholarly' installiert ist.
    """
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs("test")
        _ = next(search_results)  # Wenn wir 1 Ergebnis ziehen können, klappt es
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
        return "data" in data
    except Exception:
        return False

def check_openalex_connection(timeout=5):
    """
    Prüft Verbindung zu OpenAlex (works-Endpoint).
    """
    url = "https://api.openalex.org/works"
    params = {"search": "test", "per-page": 1}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "results" in data
    except Exception:
        return False

def check_core_connection(api_key="", timeout=5):
    """
    Prüft Verbindung zu CORE. Benötigt einen CORE-API-Key in st.secrets['CORE_API_KEY'] 
    oder Übergabe als Parameter.
    """
    if not api_key:
        return False
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

##############################################################################
# 2) Hauptfunktion: Wird vom Hauptmenü aufgerufen
##############################################################################

def module_online_api_filter():
    """
    Diese Funktion zeigt dem Nutzer sechs Checkboxen (PubMed/Europe PMC/Google Scholar/
    Semantic Scholar/OpenAlex/CORE). Danach kann er per Button die Verbindung prüfen –
    für jede aktivierte API wird ein grüner oder roter Punkt in einer Zeile ausgegeben.
    """
    st.title("API-Auswahl & Verbindungstest")

    st.write("Aktiviere die gewünschten APIs und klicke auf 'Verbindung prüfen'.")

    # Wir machen 2 Columns, jede mit 3 Checkboxen
    col1, col2 = st.columns(2)

    with col1:
        use_pubmed = st.checkbox("PubMed", value=True)
        use_epmc = st.checkbox("Europe PMC", value=True)
        use_google = st.checkbox("Google Scholar", value=False)

    with col2:
        use_semantic = st.checkbox("Semantic Scholar", value=False)
        use_openalex = st.checkbox("OpenAlex", value=False)
        use_core = st.checkbox("CORE", value=False)

    # Button für Verbindungstest
    if st.button("Verbindung prüfen"):
        # Kleine Hilfsfunktionen für grüne/rote Punkte
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"

        dots_list = []  # wir sammeln die Ergebnisse als HTML-Snippets

        # PubMed
        if use_pubmed:
            if check_pubmed_connection():
                dots_list.append(f"{green_dot()} <strong>PubMed</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>PubMed</strong>: FAIL")

        # Europe PMC
        if use_epmc:
            if check_europe_pmc_connection():
                dots_list.append(f"{green_dot()} <strong>Europe PMC</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Europe PMC</strong>: FAIL")

        # Google Scholar
        if use_google:
            if check_google_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Google Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Google Scholar</strong>: FAIL")

        # Semantic Scholar
        if use_semantic:
            if check_semantic_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Semantic Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Semantic Scholar</strong>: FAIL")

        # OpenAlex
        if use_openalex:
            if check_openalex_connection():
                dots_list.append(f"{green_dot()} <strong>OpenAlex</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>OpenAlex</strong>: FAIL")

        # CORE
        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            if check_core_connection(core_api_key):
                dots_list.append(f"{green_dot()} <strong>CORE</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>CORE</strong>: FAIL (API Key nötig?)")

        # Falls überhaupt keine API ausgewählt wurde
        if not dots_list:
            st.info("Keine API ausgewählt. Bitte mindestens eine ankreuzen.")
        else:
            # Nebeneinander in einer einzigen Zeile:
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)
    else:
        st.write("Bitte wähle mindestens eine API aus und klicke auf 'Verbindung prüfen'.")
