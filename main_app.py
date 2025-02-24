import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

#############################################
# Hilfsfunktionen (Checks + Search)
#############################################
class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=100):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = []
            for key, value in (filters or {}).items():
                filter_expressions.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort
        r = requests.get(self.base_url + endpoint, headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

def check_core_aggregate_connection(api_key, timeout=15):
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def check_pubmed_connection(timeout=10):
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except:
        return False

def check_europe_pmc_connection(timeout=10):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except:
        return False

#############################################
# Sonstige
#############################################
def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")

#############################################
# API SELECTION (Checkbox-Version mit Farbe)
#############################################
def page_api_selection():
    st.title("API Selection & Connection Status (mit Farbe)")

    st.markdown(
        """
        <style>
        /* Mache den Confirm-Button grün */
        div.stButton > button:first-child {
            background-color: green;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # APIs, die wir anbieten
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    
    # SessionState
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = []

    st.write("Bitte wähle deine APIs über Checkboxen:")

    # Schleife über alle APIs
    for api in all_apis:
        # Ist diese API in st.session_state["selected_apis"]?
        is_currently_checked = (api in st.session_state["selected_apis"])

        # Checkbox zeichnen
        cb_state = st.checkbox(api, value=is_currently_checked, key=f"chk_{api}")

        # Wenn der User sie jetzt ausgewählt hat, machen wir den Connection-Check:
        if cb_state:
            # Falls API noch nicht in selected_apis => hinzufügen
            if api not in st.session_state["selected_apis"]:
                st.session_state["selected_apis"].append(api)

            # Hier den Check
            # Nur bedingt echtes Checking, wir zeigen Demonstration:
            # - PubMed => check_pubmed_connection()
            # - Europe PMC => check_europe_pmc_connection()
            # - CORE => check_core_aggregate_connection()
            # => Falls OK => grün, sonst rot
            success = False
            if api == "PubMed":
                success = check_pubmed_connection()
            elif api == "Europe PMC":
                success = check_europe_pmc_connection()
            elif api == "CORE Aggregate":
                core_key = st.secrets.get("CORE_API_KEY", "")
                if core_key:
                    success = check_core_aggregate_connection(core_key)
                else:
                    success = False
            else:
                # Z. B. bei "OpenAlex", "Google Scholar", "Semantic Scholar"
                # (noch kein Check implementiert => wir tun so, als ob immer FAIL)
                success = False

            # Hintergrundfarbe basierend auf success
            if success:
                color = "green"
                txt = "OK"
            else:
                color = "red"
                txt = "FAIL (No valid check or no connection)"

            st.markdown(
                f"<div style='background-color:{color}; color:white; padding:6px; margin-bottom:8px;'>"
                f"{api} connection -> {txt}</div>",
                unsafe_allow_html=True
            )
        else:
            # Falls das Häkchen entfernt wurde -> aus st.session_state entfernen
            if api in st.session_state["selected_apis"]:
                st.session_state["selected_apis"].remove(api)

            st.write(f"{api} is not selected")

    st.write("---")
    # Bestätigungs-Button
    if st.button("Confirm selection"):
        st.success(f"Final selection: {st.session_state['selected_apis']}")
    
    st.write("---")
    # Zurück
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    st.write("Configure codewords, synonyms, etc. for your PubMed search. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_paper_selection():
    st.title("Paper Selection Settings")
    st.write("Define how you want to pick or exclude certain papers. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_analysis():
    st.title("Analysis & Evaluation Settings")
    st.write("Set up your analysis parameters, thresholds, etc. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_extended_topics():
    st.title("Extended Topics")
    st.write("Access advanced or extended topics for further research. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

# -----------------Sidebar & NAV-------------------
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")

    pages = {
        "Home": page_home,
        "1) API Selection": page_api_selection,
        "2) Online Filter": page_online_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics
    }
    # Buttons
    for label in pages.keys():
        if st.sidebar.button(label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    return pages[st.session_state["current_page"]]


def main():
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    page_fn = sidebar_module_navigation()
    page_fn()

if __name__ == '__main__':
    main()
