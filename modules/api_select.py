import streamlit as st
import requests

#############################################
# Module: API Selection and Connection Checks
#############################################
def module_api_select():
    st.header("Modul 1: Wähle APIs aus")

    # Define the available API options
    options = [
        "Europe PMC",
        "PubMed",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar",
        "CORE Aggregate"
    ]
    
    # Use a multi-select widget to let the user choose the APIs
    selected_apis = st.multiselect("Welche APIs möchtest du nutzen?", options, default=["Europe PMC"])
    
    # Save the selected APIs to session state so they can be used elsewhere
    st.session_state["selected_apis"] = selected_apis

    st.write("Aktuell ausgewählt:", selected_apis)

    # Check connections for selected APIs
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
# Main Streamlit App
#############################################
def main():
    st.title("API Connection Checker")
    module_api_select()

if __name__ == '__main__':
    main()
