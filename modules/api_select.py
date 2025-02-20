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
# Draw the API Selection Bar (persistent at the top)
#############################################
def draw_api_selection_bar():
    # Use a container and HTML styling to create a green bar that spans the full width.
    # Note: interactive widgets cannot be placed directly inside st.markdown, so we create a container.
    with st.container():
        st.markdown(
            """
            <style>
            .api-bar {
                background-color: green;
                padding: 10px;
                width: 100%;
                min-height: 3cm;
                display: flex;
                align-items: center;
            }
            .api-bar h2 {
                color: white;
                margin: 0 20px 0 0;
            }
            </style>
            <div class="api-bar">
                <h2>API Selection</h2>
            </div>
            """,
            unsafe_allow_html=True
        )
        # Now add the API multiselect below the green header so that it remains at the top.
        # Use session_state to preserve selection.
        options = [
            "Europe PMC",
            "PubMed",
            "CORE Aggregate",
            "OpenAlex",
            "Google Scholar",
            "Semantic Scholar"
        ]
        if "selected_apis" not in st.session_state:
            st.session_state["selected_apis"] = ["Europe PMC"]
        selected_apis = st.multiselect("Select APIs to use:", options, default=st.session_state["selected_apis"])
        st.session_state["selected_apis"] = selected_apis

        # Display the current selection in a subheader with green background
        if selected_apis:
            selected_str = ", ".join(selected_apis)
            st.markdown(
                f"<div style='background-color: green; color: white; padding: 5px;'>Currently selected APIs: {selected_str}</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='background-color: red; color: white; padding: 5px;'>No APIs selected!</div>",
                unsafe_allow_html=True
            )
        
        # Check connections for selected APIs and display the results in the same container.
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
            # Retrieve CORE API key from Streamlit secrets
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
    
    # Draw the persistent API Selection Bar at the top.
    draw_api_selection_bar()
    
    st.write("This app checks the connections for the selected APIs.")
    st.write("The API selection above remains visible even if you navigate to other modules.")
    
    # (Additional modules or app logic can be added here.)
    st.write("You can now build further modules that use the selected API list from the session state.")
    
if __name__ == '__main__':
    main()
