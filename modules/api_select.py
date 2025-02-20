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
# Module: API Selection and Connection Checks
#############################################
def module_api_select():
    st.header("Module 1: Select APIs to Use")

    # Define available API options
    options = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    
    # Multi-select widget to let user choose APIs; default selects Europe PMC
    selected_apis = st.multiselect("Which APIs do you want to use?", options, default=["Europe PMC"])
    
    # Save selected APIs in session state
    st.session_state["selected_apis"] = selected_apis
    st.write("Currently selected:", selected_apis)

    # Check each selected API connection
    if "PubMed" in selected_apis:
        if check_pubmed_connection():
            st.success("PubMed connection established!")
        else:
            st.error("PubMed connection failed!")
    
    if "Europe PMC" in selected_apis:
        if check_europe_pmc_connection():
            st.success("Europe PMC connection established!")
        else:
            st.error("Europe PMC connection failed!")
    
    if "CORE Aggregate" in selected_apis:
        # Provide your CORE Aggregate API key here:
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.success("CORE Aggregate connection established!")
        else:
            st.error("CORE Aggregate connection failed!")

#############################################
# Main Streamlit App
#############################################
def main():
    st.title("API Connection Checker")
    module_api_select()

if __name__ == '__main__':
    main()
