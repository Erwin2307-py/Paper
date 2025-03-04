# modules/online_api_filter.py

import streamlit as st
import requests
import openai  # Wichtig: 'openai' installieren (pip install openai)

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
        return ("resultList" in data and "result" in data["resultList"])
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
    Prüft Verbindung zu CORE. Benötigt einen CORE-API-Key in st.secrets['CORE_API_KEY'].
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

def check_chatgpt_connection():
    """
    Prüft, ob ChatGPT (openai) erreichbar ist, indem ein sehr kurzer Prompt
    an gpt-3.5-turbo gesendet wird. Benötigt openai.api_key in st.secrets['OPENAI_API_KEY'].
    Achtung: Verbraucht ein paar Tokens.
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return False
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user", "content":"Short connectivity test. Reply with any short message."}],
            max_tokens=10,
            temperature=0
        )
        # Wenn kein Fehler auftrat, gehen wir davon aus, dass die Verbindung OK ist.
        return True
    except Exception:
        return False


##############################################################################
# 2) Hauptfunktion: Wird vom Hauptmenü aufgerufen
##############################################################################

def module_online_api_filter():
    """
    Diese Funktion zeigt dem Nutzer sieben Checkboxen (PubMed, Europe PMC,
    Google Scholar, Semantic Scholar, OpenAlex, CORE, ChatGPT). Danach kann
    er per Button die Verbindung prüfen – für jede aktivierte API / ChatGPT
    wird ein grüner oder roter Punkt in einer Zeile ausgegeben.
    """
    st.title("API-Auswahl & Verbindungstest")

    st.write("Aktiviere die gewünschten APIs und klicke auf 'Verbindung prüfen'.")

    # Wir machen 2 Columns, 4 in einer, 3 in der anderen
    col1, col2 = st.columns(2)

    with col1:
        use_pubmed = st.checkbox("PubMed", value=True)
        use_epmc = st.checkbox("Europe PMC", value=True)
        use_google = st.checkbox("Google Scholar", value=False)
        use_semantic = st.checkbox("Semantic Scholar", value=False)

    with col2:
        use_openalex = st.checkbox("OpenAlex", value=False)
        use_core = st.checkbox("CORE", value=False)
        use_chatgpt = st.checkbox("ChatGPT", value=False)

    # Button für Verbindungstest
    if st.button("Verbindung prüfen"):
        # Kleine Hilfsfunktionen für grüne/rote Punkte
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"

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

        # OpenAlex
        if use_openalex:
            ok = check_openalex_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>OpenAlex</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>OpenAlex</strong>: FAIL")

        # CORE
        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            ok = check_core_connection(core_api_key)
            if ok:
                dots_list.append(f"{green_dot()} <strong>CORE</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>CORE</strong>: FAIL (Key nötig?)")

        # ChatGPT
        if use_chatgpt:
            ok = check_chatgpt_connection()
            if ok:
                dots_list.append(f"{green_dot()} <strong>ChatGPT</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>ChatGPT</strong>: FAIL (API-Key nötig?)")

        # Falls überhaupt keine API/ChatGPT ausgewählt
        if not dots_list:
            st.info("Keine Option ausgewählt. Bitte mindestens eine ankreuzen.")
        else:
            # Nebeneinander in einer einzigen Zeile:
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)
    else:
        st.write("Bitte wähle mindestens eine API / ChatGPT aus und klicke auf 'Verbindung prüfen'.")
