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
# Search Functions for APIs
#############################################
def search_europe_pmc(query):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 10}
    results = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "resultList" in data and "result" in data["resultList"]:
            for item in data["resultList"]["result"]:
                results.append({
                    "Source": "Europe PMC",
                    "Title": item.get("title", "n/a"),
                    "Author": item.get("authorString", "n/a"),
                    "Journal": item.get("journalTitle", "n/a"),
                    "Year": item.get("pubYear", "n/a")
                })
    except Exception as e:
        st.error(f"Europe PMC search error: {e}")
    return results

def search_pubmed(query):
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 10}
    results = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        idlist = js.get("esearchresult", {}).get("idlist", [])
        for pmid in idlist:
            results.append({
                "Source": "PubMed",
                "PMID": pmid,
                "Title": f"Paper with PMID {pmid}"
            })
    except Exception as e:
        st.error(f"PubMed search error: {e}")
    return results

def search_core_aggregate(query):
    CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
    results = []
    try:
        if CORE_API_KEY:
            core = CoreAPI(CORE_API_KEY)
            data = core.search_publications(query, limit=10)
            if "results" in data:
                for pub in data["results"]:
                    results.append({
                        "Source": "CORE Aggregate",
                        "Title": pub.get("title", "n/a"),
                        "DOI": pub.get("doi", "n/a")
                    })
    except Exception as e:
        st.error(f"CORE Aggregate search error: {e}")
    return results

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
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "your_core_api_key_here")
        if CORE_API_KEY and check_core_aggregate_connection(CORE_API_KEY):
            st.sidebar.success("CORE Aggregate connection established!")
        else:
            st.sidebar.error("CORE Aggregate connection failed!")

#############################################
# Main Streamlit App
#############################################
def main():
    # Grüner Balken oben (3 cm hoch, volle Breite)
    st.markdown(
        """
        <div style="background-color: green; width: 100%; height: 3cm;"></div>
        """,
        unsafe_allow_html=True
    )
    
    st.title("API Connection & Search Checker")
    
    # Always display the API selection sidebar so that the choices remain visible
    module_api_select()
    
    st.write("This app checks the connections for selected APIs and allows you to run a test search query.")
    
    # Suchanfrage-Eingabefeld und Such-Button
    query = st.text_input("Enter a search query to test the API:", "")
    if st.button("Search"):
        if not query.strip():
            st.warning("Please enter a search query.")
        else:
            all_results = []
            selected = st.session_state.get("selected_apis", [])
            
            if "Europe PMC" in selected:
                res_epmc = search_europe_pmc(query)
                all_results.extend(res_epmc)
            if "PubMed" in selected:
                res_pubmed = search_pubmed(query)
                all_results.extend(res_pubmed)
            if "CORE Aggregate" in selected:
                res_core = search_core_aggregate(query)
                all_results.extend(res_core)
            # Hier können weitere API-Suchfunktionen ergänzt werden...
            
            if all_results:
                st.success(f"Found {len(all_results)} result(s).")
                st.dataframe(all_results)
            else:
                st.info("No results found or search failed for the selected APIs.")

if __name__ == '__main__':
    main()
