import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

#############################################
# CORE Aggregate API Class and Connection Check
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

def search_core_aggregate(query):
    CORE_API_KEY = st.secrets.get("CORE_API_KEY", "")
    if not CORE_API_KEY:
        return []
    try:
        core = CoreAPI(CORE_API_KEY)
        raw = core.search_publications(query, limit=100)
        out = []
        results = raw.get("results", [])
        for item in results:
            title = item.get("title", "n/a")
            year = str(item.get("yearPublished", "n/a"))
            journal = item.get("publisher", "n/a")
            out.append({
                "PMID": "n/a",
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"CORE search error: {e}")
        return []

#############################################
# PubMed Connection Check + Search
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
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
    out = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return out
        
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        summary_data = r2.json().get("result", {})

        for pmid in idlist:
            info = summary_data.get(pmid, {})
            title = info.get("title", "n/a")
            pubdate = info.get("pubdate", "")
            year = pubdate[:4] if pubdate else "n/a"
            journal = info.get("fulljournalname", "n/a")
            out.append({
                "PMID": pmid,
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

def fetch_pubmed_abstract(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = []
        for elem in root.findall(".//AbstractText"):
            if elem.text:
                abs_text.append(elem.text.strip())
        if abs_text:
            return "\n".join(abs_text)
        else:
            return "(No abstract available)"
    except Exception as e:
        return f"(Error: {e})"

#############################################
# Europe PMC Connection Check + Search
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

def search_europe_pmc(query):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": 100,
        "resultType": "core"
    }
    out = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "resultList" not in data or "result" not in data["resultList"]:
            return out
        results = data["resultList"]["result"]
        for item in results:
            pmid = item.get("pmid", "n/a")
            title = item.get("title", "n/a")
            year = str(item.get("pubYear", "n/a"))
            journal = item.get("journalTitle", "n/a")

            out.append({
                "PMID": pmid if pmid else "n/a",
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return out
    except Exception as e:
        st.error(f"Europe PMC search error: {e}")
        return []

#############################################
# Excel-Hilfsfunktion
#############################################
import pandas as pd
from io import BytesIO

def convert_results_to_excel(data):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
        try:
            writer.save()
        except:
            pass
    return output.getvalue()

#############################################
# Pages
#############################################

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")

def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    st.write("Configure codewords, synonyms, etc. for your PubMed search. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_paper_selection():
    st.title("Paper Selection Settings")
    st.write("Define how you want to pick or exclude certain papers. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_analysis():
    st.title("Analysis & Evaluation Settings")
    st.write("Set up your analysis parameters, thresholds, etc. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_extended_topics():
    st.title("Extended Topics")
    st.write("Access advanced or extended topics for further research. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

#############################################
# "Api_select" in neuem Fenster öffnen
#############################################

def open_api_select_in_new_window():
    """
    Zeigt ein JavaScript-Snippet an, das in einem neuen Browser-Tab/Fenster 
    eine andere Streamlit-App (z. B. 'api_select') öffnet.
    
    -> Du musst natürlich eine URL haben, wo dein 'api_select' läuft. 
       z. B. http://localhost:8502/ oder ähnliches.
    """
    new_window_url = "http://localhost:8502"  # BEISPIEL: du bräuchtest dein API Select.
    st.markdown(
        f"""
        <script>
        window.open("{new_window_url}", "_blank");
        </script>
        """, unsafe_allow_html=True
    )

#############################################
# Sidebar Module Navigation
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")

    # Wir machen hier alles so wie vorher, aber 
    # bei "1) API Selection" öffnen wir per JavaScript ein neues Fenster.
    
    if st.sidebar.button("Home"):
        st.session_state["current_page"] = "Home"
    elif st.sidebar.button("1) API Selection"):
        # HIER: stattdessen neues Fenster
        open_api_select_in_new_window()
        # Optional: st.session_state["current_page"] = "Home"
        # oder man bleibt auf der alten Seite
    elif st.sidebar.button("2) Online Filter"):
        st.session_state["current_page"] = "2) Online Filter"
    elif st.sidebar.button("3) Codewords & PubMed"):
        st.session_state["current_page"] = "3) Codewords & PubMed"
    elif st.sidebar.button("4) Paper Selection"):
        st.session_state["current_page"] = "4) Paper Selection"
    elif st.sidebar.button("5) Analysis & Evaluation"):
        st.session_state["current_page"] = "5) Analysis & Evaluation"
    elif st.sidebar.button("6) Extended Topics"):
        st.session_state["current_page"] = "6) Extended Topics"

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

def render_page():
    # Pseudocode: je nach st.session_state["current_page"] 
    # unsere page-Funktionen aufrufen
    if st.session_state["current_page"] == "Home":
        page_home()
    elif st.session_state["current_page"] == "2) Online Filter":
        page_online_filter()
    elif st.session_state["current_page"] == "3) Codewords & PubMed":
        page_codewords_pubmed()
    elif st.session_state["current_page"] == "4) Paper Selection":
        page_paper_selection()
    elif st.session_state["current_page"] == "5) Analysis & Evaluation":
        page_analysis()
    elif st.session_state["current_page"] == "6) Extended Topics":
        page_extended_topics()
    else:
        # Standard fallback: Home
        page_home()

#############################################
# Main Streamlit App
#############################################
def main():
    # CSS
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

    # Sidebar
    sidebar_module_navigation()

    # Haupt-Rendering
    render_page()

if __name__ == '__main__':
    main()
