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
        # Details über eSummary abrufen
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
    
    selected_apis = st.sidebar.multiselect("Which APIs do you want to use?", options, default=st.session_state["selected_apis"])
    st.session_state["selected_apis"] = selected_apis  
    st.sidebar.write("Currently selected:", selected_apis)

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
# Excel Download Funktion
#############################################
def convert_results_to_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
        writer.save()
    return output.getvalue()

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
    
    # Top Green Bar
    st.markdown(
        """
        <div style="background-color: green; width: 100%; height: 3cm; margin: 0; padding: 0;"></div>
        """,
        unsafe_allow_html=True
    )
    
    st.title("API Connection Checker & PubMed Search")
    
    module_api_select()
    
    st.write("This app checks API connections and provides a PubMed search module. The search results remain stable.")
    
    # --- PubMed Search ---
    st.header("Search PubMed")
    search_query = st.text_input("Enter a search query for PubMed:")
    
    if st.button("Search"):
        if not search_query.strip():
            st.warning("Please enter a search query.")
        else:
            results = search_pubmed(search_query)
            st.session_state["pubmed_results"] = results
            st.success(f"Found {len(results)} paper(s).")
    
    # Anzeige der Suchergebnisse (immer sichtbar, wenn vorhanden)
    if "pubmed_results" in st.session_state and st.session_state["pubmed_results"]:
        st.subheader("Search Results")
        st.table(st.session_state["pubmed_results"])
        
        # Selectbox zum Auswählen eines Papers, das hinzugefügt werden soll
        paper_options = [f"{r['Title']} (PMID: {r['PMID']})" for r in st.session_state["pubmed_results"]]
        selected_paper = st.selectbox("Select a paper to add to your selection:", paper_options, key="paper_select")
        if st.button("Add Paper"):
            if "displayed_papers" not in st.session_state:
                st.session_state["displayed_papers"] = []
            if selected_paper not in st.session_state["displayed_papers"]:
                st.session_state["displayed_papers"].append(selected_paper)
    
    # Anzeige der persistierten ausgewählten Paper und deren Abstracts in einem Expander
    with st.expander("Selected Papers Details", expanded=True):
        if "displayed_papers" in st.session_state and st.session_state["displayed_papers"]:
            selected_info = []
            for option in st.session_state["displayed_papers"]:
                try:
                    pmid = option.split("PMID: ")[1].rstrip(")")
                except IndexError:
                    pmid = ""
                if pmid:
                    abstract = fetch_pubmed_abstract(pmid)
                    selected_info.append({"Paper": option, "Abstract": abstract})
                    st.subheader(f"Abstract for PMID {pmid}")
                    st.write(abstract)
            # Download-Button für die ausgewählten Paper
            if selected_info:
                excel_data_selected = convert_results_to_excel(selected_info)
                st.download_button(
                    label="Download Selected Papers as Excel",
                    data=excel_data_selected,
                    file_name="Selected_Papers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("No papers have been added yet.")
    
    # Download-Button für alle Suchergebnisse
    if "pubmed_results" in st.session_state and st.session_state["pubmed_results"]:
        excel_data_all = convert_results_to_excel(st.session_state["pubmed_results"])
        st.download_button(
            label="Download All Search Results as Excel",
            data=excel_data_all,
            file_name="PubMed_Results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    st.write("Use the sidebar for further module navigation.")

if __name__ == '__main__':
    main()
