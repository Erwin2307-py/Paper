import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

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
# PubMed Connection Check and Search Functions
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

def search_pubmed(query):
    """Conducts a PubMed search and returns a list of dictionaries with PMID and Title."""
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 20}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return []
        # Retrieve details via eSummary
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        summary_data = r2.json()
        results = []
        for pmid in idlist:
            summ = summary_data.get("result", {}).get(pmid, {})
            title = summ.get("title", "n/a")
            results.append({"PMID": pmid, "Title": title})
        return results
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

def fetch_pubmed_abstract(pmid):
    """Fetches the abstract for a given PubMed ID using eFetch."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = ""
        for elem in root.findall(".//AbstractText"):
            if elem.text:
                abs_text += elem.text + "\n"
        return abs_text.strip() if abs_text.strip() != "" else "(No abstract available)"
    except Exception as e:
        return f"(Error fetching abstract: {e})"

#############################################
# Europe PMC Connection Check and Search Function
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
# Convert search results to Excel (for download)
#############################################
def convert_results_to_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="PubMedResults")
    return output.getvalue()

#############################################
# Top Green Bar with API Selection and Search Area
#############################################
def top_api_selection():
    # Create a full-width fixed green bar (3 cm high) at the top.
    st.markdown(
        """
        <div style="
            background-color: #8BC34A;
            width: 100vw;
            height: 3cm;
            margin: 0;
            padding: 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;">
        """,
        unsafe_allow_html=True
    )
    # API selection widget inside the green bar:
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

    # Display the selected APIs in white text inside the bar:
    st.markdown(
        f"""
        <div style="color: white; font-size: 16px;">
            Currently selected: {", ".join(selected)}
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Display connection statuses as inline labels.
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
        <div style="color: white; font-size: 16px; margin-top: 5px;">
            {status_html}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

def top_api_search_area():
    # Add padding so main content doesn't hide behind fixed bar.
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    st.header("API Search")
    search_query = st.text_input("Enter search query for PubMed:", key="pubmed_search_query")
    chosen_api = st.selectbox("Select API for search:", st.session_state.get("selected_apis", []), key="api_search_select")
    if st.button("Search", key="api_search_button"):
        if not search_query.strip():
            st.info("Please enter a search query.")
        else:
            if chosen_api == "PubMed":
                count = search_pubmed_count(search_query)
                results = search_pubmed(search_query)
            elif chosen_api == "Europe PMC":
                count = search_europe_pmc_count(search_query)
                # For demonstration, we just use count; full results can be implemented similarly.
                results = []  
            elif chosen_api == "CORE Aggregate":
                CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
                count = search_core_aggregate_count(search_query, CORE_API_KEY)
                results = []  
            else:
                st.info(f"Search functionality for {chosen_api} is not implemented.")
                return
            st.success(f"{chosen_api} reports {count} papers found for query: '{search_query}'")
            # Save results in session state so they persist
            st.session_state["pubmed_results"] = results

def search_pubmed_count(query):
    """Return count of papers for a given query in PubMed."""
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 0}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return int(data.get("esearchresult", {}).get("count", "0"))
    except Exception:
        return 0

def search_europe_pmc_count(query):
    """Return count of papers for a given query in Europe PMC."""
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 0}
    try:
        r = requests.get(test_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return int(data.get("hitCount", 0))
    except Exception:
        return 0

def search_core_aggregate_count(query, api_key):
    """Return count of papers for a given query in CORE Aggregate."""
    try:
        core = CoreAPI(api_key)
        result = core.search_publications(query, limit=1)
        return int(result.get("count", 0))
    except Exception:
        return 0

#############################################
# Sidebar Module Navigation with Vertical Buttons
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    modules = [
        ("1) API Search", "api_search"),
        ("2) Online Filter", "online_filter"),
        ("3) Codewords & PubMed", "codewords_pubmed"),
        ("4) Paper Selection", "paper_selection"),
        ("5) Analysis & Evaluation", "analysis"),
        ("6) Extended Topics", "extended_topics")
    ]
    
    for label, key in modules:
        if st.sidebar.button(label, key=key, help=label):
            st.session_state["selected_module"] = key

    if "selected_module" not in st.session_state:
        st.session_state["selected_module"] = "api_search"
    st.sidebar.write("Selected Module:", st.session_state["selected_module"])

#############################################
# Main Streamlit App
#############################################
def main():
    # Render the fixed top green bar with API selection and status.
    top_api_selection()
    
    # Render the API search area below the fixed bar.
    top_api_search_area()
    
    st.title("API Connection Checker & PubMed Search")
    st.write("This app checks API connections and allows you to search for papers using selected APIs.")
    st.write("Use the sidebar buttons to switch modules. The top green bar with API selection remains visible at all times.")
    
    sidebar_module_navigation()
    
    # For now, if the selected module is "api_search", we display the API search area.
    module = st.session_state.get("selected_module", "api_search")
    if module == "api_search":
        top_api_search_area()
    # Additional modules can be imported and called here.
    
    st.write("Selected APIs are checked above. Use the sidebar buttons to switch modules.")

if __name__ == '__main__':
    main()
