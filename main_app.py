import streamlit as st
import requests

#############################################
# Must be the very first Streamlit command!
#############################################
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

#############################################
# CORE Aggregate API Class and Connection Check
#############################################
class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=10):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = [f"{key}:{value}" for key, value in filters.items()]
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort
        r = requests.get(
            self.base_url + endpoint,
            headers=self.headers,
            params=params,
            timeout=15
        )
        r.raise_for_status()
        return r.json()

def check_core_aggregate_connection(api_key, timeout=15):
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

#############################################
# PubMed Connection Check
#############################################
def check_pubmed_connection(timeout=10):
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

#############################################
# Europe PMC Connection Check
#############################################
def check_europe_pmc_connection(timeout=10):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

#############################################
# Sidebar Module: API Selection (Persistent)
#############################################
def module_api_select():
    st.sidebar.header("Module 1: Select APIs to Use")
    
    # Available API options
    options = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    
    # Use session_state to persist the selection
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]
    
    selected_apis = st.sidebar.multiselect(
        "Which APIs do you want to use?", 
        options, 
        default=st.session_state["selected_apis"]
    )
    st.session_state["selected_apis"] = selected_apis  # update session state

    st.sidebar.write("Currently selected:", selected_apis)
    
    # Check each API connection and display a button-like status message
    if "PubMed" in selected_apis:
        if check_pubmed_connection():
            st.sidebar.button("PubMed: Connected", key="pubmed_ok", disabled=True, help="Connected", 
                              on_click=lambda: None, 
                              help_icon="✅")
        else:
            st.sidebar.button("PubMed: Not Connected", key="pubmed_fail", disabled=True, help="Failed", 
                              on_click=lambda: None, 
                              help_icon="❌")
    
    if "Europe PMC" in selected_apis:
        if check_europe_pmc_connection():
            st.sidebar.button("Europe PMC: Connected", key="europepmc_ok", disabled=True, help="Connected", 
                              on_click=lambda: None, 
                              help_icon="✅")
        else:
            st.sidebar.button("Europe PMC: Not Connected", key="europepmc_fail", disabled=True, help="Failed", 
                              on_click=lambda: None, 
                              help_icon="❌")
    
    if "CORE Aggregate" in selected_apis:
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.sidebar.button("CORE Aggregate: Connected", key="core_ok", disabled=True, help="Connected", 
                              on_click=lambda: None, 
                              help_icon="✅")
        else:
            st.sidebar.button("CORE Aggregate: Not Connected", key="core_fail", disabled=True, help="Failed", 
                              on_click=lambda: None, 
                              help_icon="❌")

#############################################
# Main Streamlit App
#############################################
def main():
    # Top fixed green bar (3cm high, flush to screen edges)
    st.markdown(
        """
        <div style="
            background-color: #8BC34A;
            width: 100vw;
            height: 3cm;
            margin: 0;
            padding: 0;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;">
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Add padding at the top so content does not hide under the fixed bar
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker")
    st.write("This app checks the connections for selected APIs. Use the sidebar above to select which APIs to test.")
    
    # Always display the API selection sidebar
    module_api_select()
    
    # (You can add further content or module navigation below.)
    st.write("Selected APIs are automatically tested. The buttons above indicate the connection status for each API.")

if __name__ == '__main__':
    main()

