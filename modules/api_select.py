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

    def search_publications(self, query, filters=None, sort=None, limit=20):
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
    """
    Führt eine PubMed-Suche durch und gibt eine Liste mit Titel und PMID zurück.
    """
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 20}
    out = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return out
        
        # Abrufen weiterer Metadaten via eSummary
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        summary_data = r2.json()
        
        for pmid in idlist:
            summ = summary_data.get("result", {}).get(pmid, {})
            title = summ.get("title", "n/a")
            out.append({"PMID": pmid, "Title": title})
        return out
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
# Excel-Hilfsfunktion
#############################################
import pandas as pd
from io import BytesIO

def convert_results_to_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="PubMedResults")
        writer.save()
    return output.getvalue()


#############################################
# Module API Selection (Sidebar)
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

    # Check connections
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
    if "CORE Aggregate" in selected_apis:
        CORE_API_KEY = st.secrets.get("CORE_API_KEY", "")
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
# CORE Search-Funktion
#############################################
def search_core_aggregate(query):
    """
    Sucht (limit=20) Paper in CORE. Gibt pro Paper 'PMID': 'n/a', 'Title':..., 
    um dieselbe Struktur wie PubMed zu haben.
    """
    CORE_API_KEY = st.secrets.get("CORE_API_KEY", "")
    if not CORE_API_KEY:
        return []
    try:
        core = CoreAPI(CORE_API_KEY)
        raw = core.search_publications(query, limit=20)
        results = raw.get("results", [])
        out = []
        for item in results:
            title = item.get("title","n/a")
            # CORE hat keine PMID -> 'n/a'
            out.append({"PMID":"n/a","Title":title})
        return out
    except Exception as e:
        st.error(f"Error searching CORE: {e}")
        return []


#############################################
# Main Streamlit App
#############################################
def main():
    st.title("API Connection Checker & Combined Paper Search")

    # Sidebar
    module_api_select()
    
    st.write("This app lets you select 'PubMed' or 'CORE Aggregate' and then search them. Each search returns a separate table. If you want more advanced combination logic, you can adapt it accordingly. For now, we show them separately.")
    
    # --- PubMed Search ---
    st.subheader("PubMed Search")
    if "pubmed_results" not in st.session_state:
        st.session_state["pubmed_results"] = []
    if "selected_pubmed" not in st.session_state:
        st.session_state["selected_pubmed"] = []

    q_pubmed = st.text_input("Enter a PubMed search query", key="query_pubmed")
    if st.button("Search PubMed"):
        # Nur wenn PubMed ausgewählt
        if "PubMed" in st.session_state["selected_apis"]:
            res = search_pubmed(q_pubmed)
            st.session_state["pubmed_results"] = res
            st.write(f"Found {len(res)} PubMed paper(s).")
        else:
            st.info("PubMed not selected in the sidebar. Please select it first.")
    
    if st.session_state["pubmed_results"]:
        st.table(st.session_state["pubmed_results"])
        
        # Multiselect
        options_pub = [f"{r['Title']} (PMID: {r['PMID']})" for r in st.session_state["pubmed_results"]]
        sel_pub = st.multiselect("Select paper(s) to see abstract:", options_pub, key="pubmed_multisel")
        st.session_state["selected_pubmed"] = sel_pub
        
        selected_pubdata = []
        for item in st.session_state["selected_pubmed"]:
            pmid = item.split("PMID: ")[1].rstrip(")")
            abst = fetch_pubmed_abstract(pmid)
            st.subheader(f"Abstract (PMID {pmid})")
            st.write(abst)
            selected_pubdata.append({"PMID": pmid, "Title": item.split(" (PMID")[0]})
        
        # Download
        if st.session_state["pubmed_results"]:
            excel_pub_all = convert_results_to_excel(st.session_state["pubmed_results"])
            st.download_button(
                label="Download all PubMed results",
                data=excel_pub_all,
                file_name="All_PubMed_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        if selected_pubdata:
            excel_pub_sel = convert_results_to_excel(selected_pubdata)
            st.download_button(
                label="Download selected PubMed results",
                data=excel_pub_sel,
                file_name="Selected_PubMed_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.write("---")
    
    # --- CORE Search ---
    st.subheader("CORE Aggregate Search")
    if "core_results" not in st.session_state:
        st.session_state["core_results"] = []
    if "selected_core" not in st.session_state:
        st.session_state["selected_core"] = []
    
    q_core = st.text_input("Enter a CORE search query", key="query_core")
    if st.button("Search CORE"):
        if "CORE Aggregate" in st.session_state["selected_apis"]:
            core_key = st.secrets.get("CORE_API_KEY","")
            if not core_key:
                st.error("No CORE_API_KEY found in secrets. Please add it or deselect 'CORE Aggregate'.")
            else:
                core_res = search_core_aggregate(q_core)
                st.session_state["core_results"] = core_res
                st.write(f"Found {len(core_res)} CORE paper(s).")
        else:
            st.info("CORE Aggregate not selected in the sidebar.")
    
    if st.session_state["core_results"]:
        st.table(st.session_state["core_results"])
        opts_core = [f"{r['Title']} (NoPMID)" for r in st.session_state["core_results"]]
        sel_core = st.multiselect("Select CORE paper(s) to see details:", opts_core, key="core_multisel")
        st.session_state["selected_core"] = sel_core

        selcdata = []
        for item in st.session_state["selected_core"]:
            # We have "Title (NoPMID)"
            title = item.rsplit(" (NoPMID",1)[0]
            found = None
            for r in st.session_state["core_results"]:
                if r["Title"] == title:
                    found = r
                    break
            if found:
                st.subheader(f"Title: {found['Title']}")
                st.write("**Abstract:** (Not from CORE, none available)")
                selcdata.append(found)

        # Download
        if st.session_state["core_results"]:
            excel_core_all = convert_results_to_excel(st.session_state["core_results"])
            st.download_button(
                label="Download all CORE results",
                data=excel_core_all,
                file_name="All_CORE_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        if selcdata:
            excel_core_sel = convert_results_to_excel(selcdata)
            st.download_button(
                label="Download selected CORE results",
                data=excel_core_sel,
                file_name="Selected_CORE_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.write("Use the sidebar for further module navigation.")


if __name__ == "__main__":
    main()

