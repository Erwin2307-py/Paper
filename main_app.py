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
# CORE Aggregate API Class
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
        # Test mit 100
        result = core.search_publications("test", limit=100)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query):
    """
    Holt 100 Paper aus CORE Aggregate (sofern API-Key vorhanden).
    Gibt Liste aus Dicts zurück, z. B. [{"Title":..., "PMID":"n/a", "Year":..., ...}, ...]
    """
    CORE_API_KEY = st.secrets.get("CORE_API_KEY", "")
    if not CORE_API_KEY:
        return []
    try:
        core = CoreAPI(CORE_API_KEY)
        raw = core.search_publications(query, limit=100)
        out = []
        results = raw.get("results", [])
        for item in results:
            # Title
            title = item.get("title", "n/a")
            # Year
            year = str(item.get("yearPublished", "n/a"))
            # Scheinbares "Journal"? => publisher
            journal = item.get("publisher", "n/a")
            # CORE hat keine PMID => "n/a"
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
    """
    Holt 100 Paper aus PubMed.
    Gibt Liste aus Dicts zurück: [{"PMID":..., "Title":..., "Year":..., "Journal":...}, ...]
    """
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
    """Holt das Abstract via efetch."""
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
    # pageSize=100
    params = {"query": "test", "format": "json", "pageSize": 100}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

def search_europe_pmc(query):
    """
    Holt 100 Paper aus Europe PMC.
    Gibt Liste aus Dicts zurück: [{"PMID":..., "Title":..., "Year":..., "Journal":...}, ...]
    """
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
            pmid = item.get("pmid", "n/a")  # Falls existiert
            title = item.get("title", "n/a")
            year = item.get("pubYear", "n/a")
            journal = item.get("journalTitle", "n/a")
            
            out.append({
                "PMID": pmid if pmid else "n/a",
                "Title": title,
                "Year": str(year),
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

def convert_to_excel(data):
    """
    data: Liste von Dicts, z.B. [{"PMID":..., "Title":..., "Year":..., "Journal":..., "Abstract":...}, ...]
    """
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="PubMed")
        try:
            writer.save()
        except:
            pass
    return output.getvalue()

#############################################
# Top Green Bar with API Selection
#############################################
def top_api_selection():
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

    st.markdown(
        f"""
        <div style="color: white; font-size: 16px; margin-top: 10px;">
            Currently selected: {", ".join(selected)}
        </div>
        """,
        unsafe_allow_html=True
    )

    # Connection checks
    status_msgs = []
    if "PubMed" in selected:
        if check_pubmed_connection():
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>PubMed: OK (100 results)</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>PubMed: Fail</span>")
    if "Europe PMC" in selected:
        if check_europe_pmc_connection():
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>Europe PMC: OK (100 results)</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>Europe PMC: Fail</span>")
    if "CORE Aggregate" in selected:
        if check_core_aggregate_connection(st.secrets.get("CORE_API_KEY", "")):
            status_msgs.append("<span style='background-color: darkgreen; color: white; padding: 5px; margin-right: 5px;'>CORE: OK (100 results)</span>")
        else:
            status_msgs.append("<span style='background-color: red; color: white; padding: 5px; margin-right: 5px;'>CORE: Fail</span>")

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
# Sidebar Module Navigation
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
    
    top_api_selection()
    
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker (100 per selected API) & Combined Results")
    st.write("Each selected API contributes 100 results. For example, PubMed + Europe PMC => 200 total. PubMed + Europe PMC + CORE => 300, usw.")
    
    sidebar_module_navigation()
    
    st.header("Search & Combine Results")
    
    if "combined_results" not in st.session_state:
        st.session_state["combined_results"] = []
    if "selected_papers" not in st.session_state:
        st.session_state["selected_papers"] = []
    
    query = st.text_input("Enter a search query:", "")
    
    if st.button("Search"):
        # Bei jedem Klick werden die Ergebnisse neu geholt und kombiniert
        combined = []
        selected_apis = st.session_state["selected_apis"]
        
        if not query.strip():
            st.warning("Please enter a search query.")
        else:
            # 1) PubMed
            if "PubMed" in selected_apis:
                pubmed_res = search_pubmed(query)
                combined.extend(pubmed_res)
            
            # 2) Europe PMC
            if "Europe PMC" in selected_apis:
                epmc_res = search_europe_pmc(query)
                combined.extend(epmc_res)
            
            # 3) CORE Aggregate
            if "CORE Aggregate" in selected_apis:
                core_res = search_core_aggregate(query)
                combined.extend(core_res)
            
            # An dieser Stelle könnten weitere APIs eingefügt werden (OpenAlex etc.),
            # sofern eine Suchfunktion existiert.
            
            st.session_state["combined_results"] = combined
            st.write(f"Total results from selected APIs: {len(combined)}")
    
    # Anzeige der kombinierten Ergebnisse
    if st.session_state["combined_results"]:
        st.subheader("All Combined Results (half-size table, e.g. 4px)")

        # Schrift um die Hälfte kleiner
        st.markdown("""
        <style>
        table, thead, tbody, tr, td, th {
            font-size: 4px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.table(st.session_state["combined_results"])
        
        # Mehrfach-Auswahl
        paper_options = [
            f"{r['Title']} (PMID: {r['PMID']})"
            for r in st.session_state["combined_results"]
        ]
        
        selected_now = st.multiselect(
            "Select paper(s) to view abstracts:",
            options=paper_options,
            default=st.session_state["selected_papers"],
            key="paper_multiselect"
        )
        st.session_state["selected_papers"] = selected_now
        
        # Anzeige + Download
        selected_details = []
        for item in st.session_state["selected_papers"]:
            try:
                pmid = item.split("PMID: ")[1].rstrip(")")
            except IndexError:
                pmid = ""
            # Nur Abstract für PubMed-PMIDs
            # Falls "n/a", haben wir kein fetch
            if pmid and pmid != "n/a":
                abstract_text = fetch_pubmed_abstract(pmid)
            else:
                abstract_text = "(No abstract / not from PubMed)"
            
            # Metadaten aus combined_results
            meta = next((x for x in st.session_state["combined_results"] if str(x["PMID"]) == pmid), {})
            if not meta:
                meta = {"Title":"n/a","Year":"n/a","Journal":"n/a"}
            
            st.subheader(f"PMID: {pmid}")
            st.write(f"**Title:** {meta.get('Title','n/a')}")
            st.write(f"**Year:** {meta.get('Year','n/a')}")
            st.write(f"**Journal:** {meta.get('Journal','n/a')}")
            st.write("**Abstract:**")
            st.write(abstract_text)
            
            selected_details.append({
                "PMID": pmid,
                "Title": meta.get("Title","n/a"),
                "Year": meta.get("Year","n/a"),
                "Journal": meta.get("Journal","n/a"),
                "Abstract": abstract_text
            })
        
        if selected_details:
            excel_bytes = convert_to_excel(selected_details)
            st.download_button(
                label="Download selected papers as Excel",
                data=excel_bytes,
                file_name="Selected_Papers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    # Module check
    module = st.session_state.get("selected_module", "api_selection")
    if module == "api_selection":
        st.info("API Selection is available in the top green bar.")
    elif module == "online_filter":
        from modules.online_filter import module_online_filter
        module_online_filter()
    elif module == "codewords_pubmed":
        from modules.codewords_pubmed import module_codewords_pubmed
        module_codewords_pubmed()
    elif module == "paper_selection":
        from modules.paper_select_remove import module_select_remove
        module_select_remove()
    elif module == "analysis":
        from modules.analysis import module_analysis
        module_analysis()
    elif module == "extended_topics":
        from modules.extended_topics import module_extended_topics
        module_extended_topics()
    
    st.write("Combined up to 100 results per selected API, e.g., 2 APIs => 200 total, 3 => 300, etc.")


if __name__ == '__main__':
    main()
