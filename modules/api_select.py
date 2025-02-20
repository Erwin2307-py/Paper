import streamlit as st
import requests

#############################################
# Connection Checks for APIs
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
# CoreAPI-Klasse for CORE Aggregate
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
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

#############################################
# Streamlit App
#############################################
def main():
    st.title("API Connection Checker")
    
    # --- API Selection at the Top (in a green header bar) ---
    st.markdown(
        "<h2 style='color: white; background-color: green; padding: 10px;'>Select APIs</h2>", 
        unsafe_allow_html=True
    )
    
    # Available API options
    options = ["Europe PMC", "PubMed", "CORE Aggregate", "OpenAlex", "Google Scholar", "Semantic Scholar"]
    selected_apis = st.multiselect("Which APIs do you want to use?", options, default=["Europe PMC"])
    
    # Save the selection in session state (so it remains visible)
    st.session_state["selected_apis"] = selected_apis
    
    # Show a green bar with the selected APIs
    if selected_apis:
        selected_str = ", ".join(selected_apis)
        st.markdown(
            f"<div style='background-color: green; color: white; padding: 10px;'>"
            f"Currently selected APIs: {selected_str}</div>",
            unsafe_allow_html=True
        )
    
    # --- API Connection Checks ---
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
        # CORE API key is stored in Streamlit secrets for security.
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.success("CORE Aggregate connection established!")
        else:
            st.error("CORE Aggregate connection failed!")
    
    # (Additional API connection checks for OpenAlex, Google Scholar, Semantic Scholar can be added here.)
    st.write("Use the selection above to check API connections.")

if __name__ == '__main__':
    main()

