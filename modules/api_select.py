import streamlit as st
import requests
import xml.etree.ElementTree as ET

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
    """Führt eine PubMed-Suche durch und gibt eine Liste mit Titel und PMID zurück."""
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 20}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return []
        # Abruf der Details über eSummary
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
    """Holt das Abstract zu einer PubMed-ID via eFetch."""
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

    # For each selected API, check connection and display a colored message.
    if "PubMed" in selected_apis:
        if check_pubmed_connection():
            st.sidebar.markdown(
                "<div style='background-color: darkgreen; color: white; padding: 5px; text-align: center;'>PubMed connection established!</div>",
                unsafe_allow_html=True
            )
        else:
            st.sidebar.markdown(
                "<div style='background-color: red; color: white; padding: 5px; text-align: center;'>PubMed connection failed!</div>",
                unsafe_allow_html=True
            )
    
    if "Europe PMC" in selected_apis:
        if check_europe_pmc_connection():
            st.sidebar.markdown(
                "<div style='background-color: darkgreen; color: white; padding: 5px; text-align: center;'>Europe PMC connection established!</div>",
                unsafe_allow_html=True
            )
        else:
            st.sidebar.markdown(
                "<div style='background-color: red; color: white; padding: 5px; text-align: center;'>Europe PMC connection failed!</div>",
                unsafe_allow_html=True
            )
    
    if "CORE Aggregate" in selected_apis:
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.sidebar.markdown(
                "<div style='background-color: darkgreen; color: white; padding: 5px; text-align: center;'>CORE Aggregate connection established!</div>",
                unsafe_allow_html=True
            )
        else:
            st.sidebar.markdown(
                "<div style='background-color: red; color: white; padding: 5px; text-align: center;'>CORE Aggregate connection failed!</div>",
                unsafe_allow_html=True
            )

#############################################
# Main Streamlit App
#############################################
def main():
    # Top Green Bar: full width, 3 cm high
    st.markdown(
        """
        <div style="background-color: green; width: 100%; height: 3cm; margin: 0; padding: 0;"></div>
        """,
        unsafe_allow_html=True
    )
    
    st.title("API Connection Checker & PubMed Search")
    
    # Always display the API selection sidebar so that the choices remain visible.
    module_api_select()
    
    st.write("This app checks the connections for selected APIs and provides a PubMed search module.")
    st.write("Use the sidebar to select and see the status of the following APIs:")
    st.write("- Europe PMC")
    st.write("- PubMed")
    st.write("- CORE Aggregate")
    st.write("- (Other options like OpenAlex, Google Scholar, Semantic Scholar are available for selection)")
    st.write("If the API connections are working, you'll see a dark green message in the sidebar.")
    
    # Suchfeld für PubMed-Suche
    st.header("Search PubMed")
    search_query = st.text_input("Enter a search query for PubMed:")
    if st.button("Search"):
        if not search_query.strip():
            st.warning("Please enter a search query.")
        else:
            results = search_pubmed(search_query)
            st.write(f"Found {len(results)} paper(s).")
            if results:
                # Zeige die Ergebnisse in einer Tabelle (Titel und PMID)
                st.table(results)
                
                # Auswahlbox, um ein Paper auszuwählen, dessen Abstract angezeigt wird.
                paper_options = [f"{r['Title']} (PMID: {r['PMID']})" for r in results]
                selected_paper = st.selectbox("Select a paper to view its abstract:", paper_options)
                try:
                    selected_pmid = selected_paper.split("PMID: ")[1].rstrip(")")
                except IndexError:
                    selected_pmid = ""
                if selected_pmid:
                    abstract = fetch_pubmed_abstract(selected_pmid)
                    st.subheader("Abstract")
                    st.write(abstract)
            else:
                st.info("No results found.")
    
    st.write("Use the sidebar buttons for further module navigation.")

if __name__ == '__main__':
    main()
