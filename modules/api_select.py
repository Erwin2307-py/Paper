# modulapi_select.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET

###############################################################################
# Verbindungstest-Funktionen für PubMed, Europe PMC und CORE
###############################################################################

def check_pubmed_connection(timeout=10):
    """
    Prüft, ob eine Verbindung zu PubMed hergestellt werden kann.
    """
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return ("esearchresult" in data)
    except Exception:
        return False

def check_europe_pmc_connection(timeout=10):
    """
    Prüft, ob eine Verbindung zu Europe PMC hergestellt werden kann.
    """
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return ("resultList" in data and "result" in data["resultList"])
    except Exception:
        return False

class CoreAPI:
    """
    Klasse für CORE Aggregate-Abfragen.
    """
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def test_connection(self):
        """
        Testet die Verbindung, indem wir nach 'test' suchen (limit=1).
        """
        try:
            url = self.base_url + "search/works"
            params = {"q": "test", "limit": 1}
            r = requests.get(url, headers=self.headers, params=params, timeout=10)
            r.raise_for_status()
            js = r.json()
            return ("results" in js)
        except:
            return False

def check_core_aggregate_connection():
    """
    Prüft, ob eine Verbindung zu CORE Aggregate möglich ist.
    Erwartet den CORE_API_KEY in st.secrets.
    """
    key = st.secrets.get("CORE_API_KEY", "")
    if not key:
        return False

    c = CoreAPI(key)
    return c.test_connection()

###############################################################################
# Haupt-Seitenfunktion: page_api_selection
###############################################################################

def page_api_selection():
    """
    Zeigt die Seite "API Selection & Connection Status" an.
    Hier verwenden wir Checkboxen (statt Dropdown), 
    prüfen bei Bedarf die Verbindung (rot/grün) 
    und speichern die Auswahl in st.session_state["selected_apis"].
    """
    st.title("API Selection & Connection Status (Modul: modulapi_select.py)")

    # Kleines CSS, um den Confirm-Button grün zu färben:
    st.markdown(
        """
        <style>
        div.stButton > button:first-child {
            background-color: green;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Liste der APIs
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate"
    ]
    # Standard-Auswahl
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]

    st.write("Bitte wähle deine APIs per Checkbox:")

    # Vorbelegung
    selected_apis_temp = set(st.session_state["selected_apis"])

    # Checkboxen + farbliche Markierung
    for api in all_apis:
        is_checked = (api in selected_apis_temp)
        cb_value = st.checkbox(api, value=is_checked, key=f"chk_{api}")

        if cb_value:
            # Verbindung testen
            connected = False
            if api == "PubMed":
                connected = check_pubmed_connection()
            elif api == "Europe PMC":
                connected = check_europe_pmc_connection()
            elif api == "CORE Aggregate":
                connected = check_core_aggregate_connection()

            if connected:
                # Grün
                st.markdown(
                    f"<div style='background-color:green; color:white; padding:4px; margin-bottom:8px;'>"
                    f"{api} -> Connection OK</div>",
                    unsafe_allow_html=True
                )
            else:
                # Rot
                st.markdown(
                    f"<div style='background-color:red; color:white; padding:4px; margin-bottom:8px;'>"
                    f"{api} -> Connection FAIL</div>",
                    unsafe_allow_html=True
                )
        else:
            st.write(f"{api} is not selected")

    st.write("---")

    # Confirm-Button: aktualisiert st.session_state["selected_apis"]
    if st.button("Confirm selection"):
        new_list = []
        for api in all_apis:
            if st.session_state.get(f"chk_{api}", False):
                new_list.append(api)
        st.session_state["selected_apis"] = new_list
        st.success(f"API selection updated: {new_list}")

    st.write("Derzeit gewählte APIs:", st.session_state["selected_apis"])

    # Back-Button
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

