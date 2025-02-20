import streamlit as st
import requests

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
            filter_expressions = []
            for key, value in filters.items():
                filter_expressions.append(f"{key}:{value}")
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
        # Try a simple search query using "test"
        result = core.search_publications("test", limit=1)
        if "results" in result:
            return True
        else:
            return False
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
        if "esearchresult" in data:
            return True
        else:
            return False
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
        if "resultList" in data and "result" in data["resultList"]:
            return True
        else:
            return False
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
    
    # Use session_state to preserve the selection
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]
    
    selected_apis = st.sidebar.multiselect("Which APIs do you want to use?", options, default=st.session_state["selected_apis"])
    st.session_state["selected_apis"] = selected_apis  # update session state

    st.sidebar.write("Currently selected:", selected_apis)

    # Check connections for selected APIs and display the result
    if "PubMed" in selected_apis:
        if check_pubmed_connection():
            st.sidebar.success("PubMed connection established!")
        else:
            st.sidebar.error("PubMed connection failed!")
    
    if "Europe PMC" in selected_apis:
        if check_europe_pmc_connection():
            st.sidebar.success("Europe PMC connection established!")
        else:
            st.sidebar.error("Europe PMC connection failed!")
    
    if "CORE Aggregate" in selected_apis:
        # Get the CORE Aggregate API key from Streamlit secrets
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.sidebar.success("CORE Aggregate connection established!")
        else:
            st.sidebar.error("CORE Aggregate connection failed!")

#############################################
# Main Streamlit App
#############################################
def main():
    # Add a large green bar at the very top of the page
    st.markdown(
        "<div style='background-color: green; color: white; padding: 10px; font-size: 24px; text-align: center;'>"
        "API Connection Checker"
        "</div>",
        unsafe_allow_html=True
    )
    
    st.title("API Connection Checker")
    
    # Always display the API selection sidebar so that the choices remain visible
    module_api_select()
    
    st.write("This app checks the connections for the selected APIs.")
    st.write("Use the sidebar to select and see the status of the following APIs:")
    st.write("- Europe PMC")
    st.write("- PubMed")
    st.write("- CORE Aggregate")
    st.write("- (Other options like OpenAlex, Google Scholar, Semantic Scholar are available for selection)")

if __name__ == '__main__':
    main()
