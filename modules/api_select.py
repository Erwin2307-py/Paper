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
# Top Green Bar with API Selection (Persistent)
#############################################
def top_api_selection():
    # Create a fixed green bar at the top with full width and 3cm height.
    st.markdown(
        """
        <div style="
            background-color: #8BC34A;
            width: 100vw;
            height: 3cm;
            margin: 0;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;">
        """,
        unsafe_allow_html=True
    )
    
    # Inside the green bar, place a multiselect widget (with hidden label) for API selection.
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
    selected = st.multiselect("Select APIs:", options, default=st.session_state["selected_apis"], key="top_api_select", label_visibility="collapsed")
    st.session_state["selected_apis"] = selected

    # Display connection status messages inside the green bar.
    messages = []
    if "PubMed" in selected:
        messages.append("PubMed: " + ("OK" if check_pubmed_connection() else "Fail"))
    if "Europe PMC" in selected:
        messages.append("Europe PMC: " + ("OK" if check_europe_pmc_connection() else "Fail"))
    if "CORE Aggregate" in selected:
        core_key = st.secrets.get("CORE_API_KEY", "")
        messages.append("CORE Aggregate: " + ("OK" if core_key and check_core_aggregate_connection(core_key) else "Fail"))
    status_msg = " | ".join(messages)
    st.markdown(
        f"""
        <div style="color: white; font-size: 16px; margin-top: 10px;">
            {status_msg}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

#############################################
# Main Streamlit App
#############################################
def main():
    # Set the page config first
    st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")
    
    # Inject CSS to remove margins so the green bar touches the screen edges.
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
    
    # Display the top fixed green bar with API selection.
    top_api_selection()
    
    # Add padding at the top so content is not hidden behind the fixed green bar.
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker")
    
    # Overall connectivity status check:
    overall_status = []
    if check_pubmed_connection():
        overall_status.append("PubMed connected")
    else:
        overall_status.append("PubMed NOT connected")
    if check_europe_pmc_connection():
        overall_status.append("Europe PMC connected")
    else:
        overall_status.append("Europe PMC NOT connected")
    core_key = st.secrets.get("CORE_API_KEY", "")
    if core_key and check_core_aggregate_connection(core_key):
        overall_status.append("CORE Aggregate connected")
    else:
        overall_status.append("CORE Aggregate NOT connected")
    
    status_overall = " | ".join(overall_status)
    st.write(f"**Overall Connectivity Status:** {status_overall}")
    
    st.write("This app checks the connections for selected APIs. Use the top green bar to select which APIs to use. The connection status is shown in the bar, and the overall connectivity is displayed below.")
    
    # (Additional modules can be added here or in the sidebar.)
    st.sidebar.title("Module Navigation")
    selection = st.sidebar.radio(
        "Select a Module:",
        (
            "1) API Selection (Top Bar)",
            "2) Online Filter",
            "3) Codewords & PubMed",
            "4) Paper Selection",
            "5) Analysis & Evaluation",
            "6) Extended Topics"
        )
    )
    
    # Call corresponding modules based on sidebar selection.
    # For example, if selection "2" is chosen, import and run module_online_filter.
    if selection.startswith("1"):
        st.info("API selection is available in the top green bar.")
    elif selection.startswith("2"):
        from modules.online_filter import module_online_filter
        module_online_filter()
    elif selection.startswith("3"):
        from modules.codewords_pubmed import module_codewords_pubmed
        module_codewords_pubmed()
    elif selection.startswith("4"):
        from modules.paper_select_remove import module_select_remove
        module_select_remove()
    elif selection.startswith("5"):
        from modules.analysis import module_analysis
        module_analysis()
    elif selection.startswith("6"):
        from modules.extended_topics import module_extended_topics
        module_extended_topics()
    
    st.write("Use the sidebar to navigate between modules. The top green bar remains visible at all times.")

if __name__ == '__main__':
    main()
