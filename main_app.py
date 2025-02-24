import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

##############################################################
# ------------------- API Checks & Searches ------------------
##############################################################

#############################################
# CORE Aggregate API
#############################################
class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=100):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = []
            for key, value in (filters or {}).items():
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
# PubMed
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
# Europe PMC
#############################################
def check_europe_pmc_connection(timeout=10):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

##############################################################
# ------------------- Excel Hilfsfunktion --------------------
##############################################################
def convert_results_to_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
        try:
            writer.save()
        except:
            pass
    return output

##############################################################
# ------------- Zusätzliche Einstellung im Hauptfenster ------
##############################################################

def main():
    st.title("API Checks & Optional Main-Area Selection")

    # 1) Wir zeigen im Hauptfenster ein Expander-Widget
    st.markdown("### API selection can also happen here (in addition to existing code/logic).")
    
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]  # Default
    
    all_apis = ["Europe PMC", "PubMed", "CORE Aggregate", "OpenAlex", "Google Scholar", "Semantic Scholar"]
    
    # Expander-Bereich
    with st.expander("Open additional API selection in main area"):
        chosen_apis = st.multiselect(
            "Select your APIs (Main Area)",
            all_apis,
            default=st.session_state["selected_apis"]
        )
        st.session_state["selected_apis"] = chosen_apis
        
        # Hier ein kleiner Verbindungstest
        st.subheader("Connection Status (Main Area Check)")
        msgs = []
        if "PubMed" in chosen_apis:
            if check_pubmed_connection():
                msgs.append("PubMed: OK")
            else:
                msgs.append("PubMed: FAIL")
        if "Europe PMC" in chosen_apis:
            if check_europe_pmc_connection():
                msgs.append("Europe PMC: OK")
            else:
                msgs.append("Europe PMC: FAIL")
        if "CORE Aggregate" in chosen_apis:
            core_key = st.secrets.get("CORE_API_KEY", "")
            if core_key and check_core_aggregate_connection(core_key):
                msgs.append("CORE: OK")
            else:
                msgs.append("CORE: FAIL (No valid key?)")
        
        if msgs:
            for m in msgs:
                st.write("- ", m)
        else:
            st.write("No APIs selected or no checks performed.")
    
    st.write("---")
    st.write("Your final selected APIs (from main area) ->", st.session_state["selected_apis"])
    st.info("You can integrate or combine this additional code with your existing logic (e.g., the sidebar approach). The above snippet does not alter your existing checks / search logic.")


if __name__ == "__main__":
    main()


