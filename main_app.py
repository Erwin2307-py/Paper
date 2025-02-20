import streamlit as st
import requests

# Must be the very first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# Inject custom CSS to remove default margins and paddings so the green bar is flush
st.markdown(
    """
    <style>
    html, body {
        margin: 0;
        padding: 0;
    }
    /* Optional: Remove extra container margins */
    .css-18e3th9, .css-1d391kg {
        margin: 0;
        padding: 0;
    }
    </style>
    """,
    unsafe_allow_html=True
)

#############################################
# Define connection-check functions and CoreAPI
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
# Top Green Bar with API Selection
#############################################
def top_api_selection():
    # This container creates a full-width green bar with a height of 3cm.
    # The API selection widget will be placed inside.
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
    # Place a multiselect widget for API selection inside the bar.
    options = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    # Use session_state to persist selection.
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]
    selected = st.multiselect("Select APIs:", options, default=st.session_state["selected_apis"], key="top_api_select",
                              label_visibility="collapsed")
    st.session_state["selected_apis"] = selected

    # Optionally, you can show a success message in the bar (e.g., connection statuses)
    messages = []
    if "PubMed" in selected:
        if check_pubmed_connection():
            messages.append("PubMed: OK")
        else:
            messages.append("PubMed: Fail")
    if "Europe PMC" in selected:
        if check_europe_pmc_connection():
            messages.append("Europe PMC: OK")
        else:
            messages.append("Europe PMC: Fail")
    if "CORE Aggregate" in selected:
        core_key = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if core_key and check_core_aggregate_connection(core_key):
            messages.append("CORE Aggregate: OK")
        else:
            messages.append("CORE Aggregate: Fail")
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
    # Call the top API selection bar so it remains fixed.
    top_api_selection()

    # Add some top padding so the content doesn't hide behind the fixed green bar.
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)

    st.title("API Connection Checker")
    st.write("This app checks the connections for selected APIs and provides several modules for further processing.")
    st.write("Use the sidebar to navigate between modules. The top green bar with API selection remains visible at all times.")

    # Sidebar navigation for additional modules.
    st.sidebar.title("Module Navigation")
    selection = st.sidebar.radio(
        "Select a Module:",
        (
            "1) API Selection (Deprecated)",
            "2) Online Filter",
            "3) Codewords & PubMed",
            "4) Paper Selection",
            "5) Analysis & Evaluation",
            "6) Extended Topics"
        
        )
    )

    # Depending on the selection, call the corresponding module.
    if selection.startswith("1"):
        # If you wish, you can call module_api_select() here,
        # but note that API selection is now at the top.
        st.info("API selection is now in the top green bar.")
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

if __name__ == '__main__':
    main()
