import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Must be the very first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# Inject custom CSS to remove default margins and paddings so the green bar is flush.
st.markdown(
    """
    <style>
    html, body {
        margin: 0;
        padding: 0;
    }
    /* Force sidebar buttons to be full width and equally sized */
    div[data-testid="stSidebar"] button {
         width: 100% !important;
         margin: 0px !important;
         padding: 10px !important;
         font-size: 16px !important;
         text-align: center !important;
         box-sizing: border-box;
    }
    </style>
    """,
    unsafe_allow_html=True
)

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
    """Conduct a PubMed search and return a list of dictionaries with 'PMID' and 'Title'."""
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 20}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return []
        # Fetch details via eSummary
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
    """Fetch the abstract for a given PubMed ID using eFetch."""
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
# Top Green Bar with API Selection (Fixed at the top)
#############################################
def top_api_selection():
    # Create a full-width green bar (3 cm high) fixed at the top.
    st.markdown(
        """
        <div style="
            background-color: #8BC34A;
            width: 100vw;
            height: 3cm;
            margin: 0;
            padding: 0;
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
        "Perplexity",
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
        <div style="color: white; font-size: 16px; margin-top: 10px;">
            Currently selected: {", ".join(selected)}
        </div>
        """,
        unsafe_allow_html=True
    )

    # Check connection statuses and display them as inline labels.
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
    if "Perplexity" in selected:
        perplexity_key = st.secrets.get("PERPLEXITY_API_KEY", "your_perplexity_api_key_here")
        if perplexity_key:
            # Here we simply check if we get a valid response from a test Perplexity query.
            test_url = "https://api.perplexity.ai/chat/completions"
            payload = {
                "model": "sonar",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 5,
                "temperature": 0
            }
            headers = {
                "Authorization": f"Bearer {perplexity_key}",
                "Content-Type": "application/json"
            }
            try:
                r = requests.post(test_url, json=payload, headers=headers, timeout=10)
                r.raise_for_status()
                data = r.json()
                if "choices" in data:
                    status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>Perplexity: OK</span>")
                else:
                    status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>Perplexity: Fail</span>")
            except Exception:
                status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>Perplexity: Fail</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>Perplexity: Fail</span>")
    status_html = " ".join(status_msgs)
    st.markdown(
        f"""
        <div style="color: white; font-size: 16px; margin-top: 10px;">
            {status_html}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

#############################################
# Sidebar Module Navigation with Vertical Buttons
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    modules = [
        ("1) API Selection", "api_selection"),
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
        st.session_state["selected_module"] = "api_selection"
    st.sidebar.write("Selected Module:", st.session_state["selected_module"])

#############################################
# Main Streamlit App
#############################################
def main():
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
    
    # Render the fixed top green bar with API selection.
    top_api_selection()
    
    # Add top padding so the main content doesn't hide behind the fixed green bar.
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker & PubMed Search")
    st.write("This app checks the connections for selected APIs and provides a PubMed search module.")
    st.write("If the API connections are working, you'll see dark green messages in the top bar.")
    
    sidebar_module_navigation()
    
    # PubMed Search Section
    st.header("Search PubMed")
    search_query = st.text_input("Enter a search query for PubMed:")
    if st.button("Search"):
        if not search_query.strip():
            st.warning("Please enter a search query.")
        else:
            results = search_pubmed(search_query)
            st.write(f"Found {len(results)} paper(s).")
            # Save results in session state so they persist.
            st.session_state["pubmed_results"] = results
    
    # Display search results if available.
    if "pubmed_results" in st.session_state and st.session_state["pubmed_results"]:
        results = st.session_state["pubmed_results"]
        st.table(results)
        
        # Allow user to select one paper to view its abstract.
        paper_options = [f"{r['Title']} (PMID: {r['PMID']})" for r in results]
        selected_paper = st.selectbox("Select a paper to view its abstract:", paper_options, key="paper_select")
        # Extract PMID from selection.
        try:
            selected_pmid = selected_paper.split("PMID: ")[1].rstrip(")")
        except IndexError:
            selected_pmid = ""
        if selected_pmid:
            abstract = fetch_pubmed_abstract(selected_pmid)
            st.subheader("Abstract")
            st.write(abstract)
    
    st.write("Use the sidebar for further module navigation.")
    st.write("Selected APIs are checked above in the top green bar.")

if __name__ == '__main__':
    main()
