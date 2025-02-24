# -------------------- api_select.py --------------------
import streamlit as st
import requests
import xml.etree.ElementTree as ET

###############################################################################
# Hier stehen die Funktionen für PubMed/Europe PMC/CORE Checks + die Page-Funktion
###############################################################################

def check_pubmed_connection(timeout=10):
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
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def test_connection(self):
        # Ein Minimal-Test
        url = self.base_url + "search/works"
        params = {"q": "test", "limit": 1}
        try:
            import requests
            r = requests.get(url, headers=self.headers, params=params, timeout=10)
            r.raise_for_status()
            js = r.json()
            return ("results" in js)
        except:
            return False

def check_core_aggregate_connection():
    # Lesen wir den KEY aus st.secrets (alternativ kann man ihn anders übergeben)
    key = st.secrets.get("CORE_API_KEY", "")
    if not key:
        return False
    c = CoreAPI(key)
    return c.test_connection()


def page_api_selection():
    """
    Zeigt alle APIs als Checkboxen an,
    markiert sie rot/grün je nach Verbindung
    und speichert die Auswahl in st.session_state["selected_apis"].
    """
    st.title("API Selection & Connection Status (Ausgelagertes Modul: api_select)")

    # Ein wenig CSS, um ggf. den Confirm-Button grün zu färben.
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

    # Liste der möglichen APIs
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate"
    ]

    # Falls noch keine Auswahl existiert
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]

    st.write("Bitte wähle die gewünschten APIs via Checkbox:")

    # Temporäre Set, um initiale Auswahl zu erkennen
    selected_apis_temp = set(st.session_state["selected_apis"])

    for api in all_apis:
        # Prüfe, ob diese API bisher ausgewählt ist
        is_checked = (api in selected_apis_temp)
        check_state = st.checkbox(api, value=is_checked, key="chk_"+api)

        # Nun machen wir eine Verbindungskontrolle, wenn checkbox = True
        # Rote = offline, Grüne = online
        if check_state:
            connected = False
            if api == "PubMed":
                connected = check_pubmed_connection()
            elif api == "Europe PMC":
                connected = check_europe_pmc_connection()
            elif api == "CORE Aggregate":
                connected = check_core_aggregate_connection()

            if connected:
                st.markdown(
                    f"<div style='background-color:green; color:white; padding:4px; margin-bottom:8px;'>"
                    f"{api} -> Connection OK</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='background-color:red; color:white; padding:4px; margin-bottom:8px;'>"
                    f"{api} -> Connection FAILED</div>",
                    unsafe_allow_html=True
                )
        else:
            st.write(f"{api} is not selected")

    st.write("---")
    # Confirm-Button
    if st.button("Confirm selection"):
        # Lese die Checkbox-Zustände aus
        new_list = []
        for api in all_apis:
            if st.session_state.get("chk_"+api, False):
                new_list.append(api)
        st.session_state["selected_apis"] = new_list
        st.success(f"API selection updated: {new_list}")

    st.write("Aktuell ausgewählte APIs:", st.session_state["selected_apis"])

    # Zurück-Button
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"
