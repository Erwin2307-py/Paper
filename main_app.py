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
# Top API Selection Bar (fixed at the top)
#############################################
def top_api_selection():
    # Create a full-width green bar at the top with a height of 3cm.
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
    # Inside the green bar, place the API multiselect.
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

    # Display connection statuses as small colored "buttons" (divs) inside the bar.
    status_msgs = []
    if "PubMed" in selected:
        if check_pubmed_connection():
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>PubMed: OK</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>PubMed: Fail</span>")
    if "Europe PMC" in selected:
        if check_europe_pmc_connection():
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>Europe PMC: OK</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>Europe PMC: Fail</span>")
    if "CORE Aggregate" in selected:
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>CORE Aggregate: OK</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>CORE Aggregate: Fail</span>")
    status_html = " ".join(status_msgs)
    st.markdown(
        f"""
        <div style="margin-top: 10px;">
            {status_html}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

#############################################
# Sidebar Module Navigation with Buttons
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    # Define modules as (Label, key) tuples.
    modules = [
        ("1) API Selection", "api_selection"),
        ("2) Online Filter", "online_filter"),
        ("3) Codewords & PubMed", "codewords_pubmed"),
        ("4) Paper Selection", "paper_selection"),
        ("5) Analysis & Evaluation", "analysis"),
        ("6) Extended Topics", "extended_topics")
    ]
    for label, key in modules:
        if st.sidebar.button(label, key=key):
            st.session_state["selected_module"] = key
    # Set a default module if not yet chosen.
    if "selected_module" not in st.session_state:
        st.session_state["selected_module"] = "api_selection"
    st.sidebar.write("Selected Module:", st.session_state["selected_module"])

#############################################
# Main Streamlit App
#############################################
def main():
    # Inject CSS to remove margins and ensure the top bar is flush.
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

    # Call the top green bar so that it remains fixed at the top.
    top_api_selection()
    
    # Add top padding so that the main content does not get hidden behind the fixed bar.
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker")
    st.write("This app checks the connections for selected APIs and provides several modules for further processing.")
    st.write("Use the sidebar to navigate between modules. The top green bar with API selection remains visible at all times.")
    
    # Sidebar navigation with buttons.
    sidebar_module_navigation()
    
    # Load the module based on the sidebar selection.
    module = st.session_state.get("selected_module", "api_selection")
    if module == "api_selection":
        st.info("API Selection is now available in the top bar.")
    elif module == "online_filter":
        from modules.online_filter import module_online_filter
        module_online_filter()
    elif module == "codewords_pubmed":
        from modules.codewords_pubmed import module_codewords_pubmed
        module_codewords_pubmed()
    elif module == "paper_selection":
        from modules.paper_select_remove import module_select_remove
        module_select_remove()
    elif module == "analysis":
        from modules.analysis import module_analysis
        module_analysis()
    elif module == "extended_topics":
        from modules.extended_topics import module_extended_topics
        module_extended_topics()
    
    st.write("Selected APIs are checked above. Use the sidebar buttons to switch modules.")
    
if __name__ == '__main__':
    main()
