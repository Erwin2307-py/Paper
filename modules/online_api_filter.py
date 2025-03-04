import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Must be the very first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

#############################################
# 1) CORE Aggregate API & Connection Check
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
        # Simple test
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query):
    """
    Returns up to 100 results from CORE (if API key exists).
    Each record is a dict: {"PMID":"n/a", "Title":..., "Year":..., "Journal":...}
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
# 2) PubMed Connection Check + Search
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
    Fetches up to 100 papers from PubMed.
    Returns a list of dicts: [{"PMID":..., "Title":..., "Year":..., "Journal":...}, ...]
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
    """Fetches the abstract from PubMed via efetch."""
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
# 3) Europe PMC Connection Check + Search
#############################################
def check_europe_pmc_connection(timeout=10):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 1}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "resultList" in data and "result" in data["resultList"]
    except Exception:
        return False

def search_europe_pmc(query):
    """
    Returns up to 100 papers from Europe PMC.
    Each record is a dict: [{"PMID":..., "Title":..., "Year":..., "Journal":...}, ...]
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
            pmid = item.get("pmid", "n/a")
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
# 4) Utility: Convert to Excel
#############################################
def convert_to_excel(data):
    """
    Convert a list of dicts into an Excel file (in memory).
    E.g. data: [{"PMID":..., "Title":..., "Year":..., "Journal":..., "Abstract":...}, ...]
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
# 5) ChatGPT Filter: filters abstracts based on keywords
#############################################
def filter_abstracts_with_chatgpt(abstracts, keywords):
    """
    Example function that sends requests to the OpenAI API to filter abstracts 
    by given keywords. 
    !!! Replace "YOUR_OPENAI_API_KEY" with your real OpenAI API key.
    !!! This example uses an older endpoint (davinci-codex).
        You might want to adjust for GPT-3.5-turbo or GPT-4, etc.
    """
    api_endpoint = "https://api.openai.com/v1/engines/davinci-codex/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer YOUR_OPENAI_API_KEY"  # <-- Put your key here
    }
    prompt_intro = f"Filter the following abstracts based on these keywords: {', '.join(keywords)}."

    results = []
    for abstract in abstracts:
        data = {
            "prompt": f"{prompt_intro}\n\nAbstract: {abstract}\n\nFiltered:",
            "max_tokens": 150,
            "n": 1,
            "stop": ["\n"]
        }
        response = requests.post(api_endpoint, headers=headers, json=data)
        if response.status_code == 200:
            result_text = response.json().get("choices", [{}])[0].get("text", "")
            # Example logic: if any keyword is found in result_text, we keep it
            if any(kw.lower() in result_text.lower() for kw in keywords):
                results.append(result_text.strip())
    return results

#############################################
# 6) A Simple "search_papers" function for module_online_filter (optional)
#############################################
def search_papers(api_name, query):
    """
    Simple example of searching each API by name, up to 100 results.
    Returns a list of dicts with some minimal info.
    (You can adapt or unify with the other search_* functions if you wish.)
    """
    results = []

    # -- PubMed -- #
    if api_name == "PubMed":
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
        response = requests.get(url, params=params)
        try:
            ids = response.json().get("esearchresult", {}).get("idlist", [])
            # For each ID, do an eSummary call (like in search_pubmed).
            if ids:
                sum_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                sum_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
                details_response = requests.get(sum_url, params=sum_params)
                summary_data = details_response.json().get("result", {})
                for pid in ids:
                    s = summary_data.get(pid, {})
                    results.append({
                        "API": "PubMed",
                        "ID": pid,
                        "Title": s.get("title", "N/A"),
                        "Year": s.get("pubdate", "N/A"),
                        "Publisher": s.get("source", "N/A")
                    })
        except Exception as e:
            st.write("PubMed-Fehler:", e)

    # -- Europe PMC -- #
    elif api_name == "Europe PMC":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {"query": query, "format": "json", "pageSize": 100}
        response = requests.get(url, params=params)
        try:
            data = response.json().get("resultList", {}).get("result", [])
            for item in data:
                results.append({
                    "API": "Europe PMC",
                    "ID": item.get("id", "N/A"),
                    "Title": item.get("title", "N/A"),
                    "Year": item.get("pubYear", "N/A"),
                    "Publisher": item.get("source", "N/A")
                })
        except Exception as e:
            st.write("Europe PMC-Fehler:", e)

    # -- CORE -- #
    elif api_name == "CORE":
        # Make sure you have your CORE key in st.secrets or inline here:
        core_key = st.secrets.get("CORE_API_KEY", "")
        if not core_key:
            st.write("Keine CORE-API gefunden (in st.secrets).")
            return results

        url = "https://api.core.ac.uk/v3/search/works"
        headers = {"Authorization": f"Bearer {core_key}"}
        params = {"q": query, "limit": 100}
        response = requests.get(url, headers=headers, params=params)
        try:
            data = response.json().get("results", [])
            for it in data:
                results.append({
                    "API": "CORE",
                    "ID": it.get("id", "N/A"),
                    "Title": it.get("title", "N/A"),
                    "Year": it.get("yearPublished", "N/A"),
                    "Publisher": it.get("publisher", "N/A")
                })
        except Exception as e:
            st.write("CORE-Fehler:", e)

    return results

#############################################
# 7) "Module 2": Online Filter
#############################################
def module_online_filter():
    st.header("Modul 2: Online-Filter")

    # -----------------------------
    # 7a) Show which APIs are active, with a green dot if online
    # -----------------------------
    st.subheader("Gewählte APIs & Verbindung")
    if "selected_apis" not in st.session_state or not st.session_state["selected_apis"]:
        st.write("Noch keine API ausgewählt oder session_state leer.")
        return

    selected_apis = st.session_state["selected_apis"]

    # We check connectivity with each:
    pubmed_ok = check_pubmed_connection() if "PubMed" in selected_apis else None
    epmc_ok = check_europe_pmc_connection() if "Europe PMC" in selected_apis else None
    core_ok = check_core_aggregate_connection(st.secrets.get("CORE_API_KEY", "")) if "CORE Aggregate" in selected_apis or "CORE" in selected_apis else None

    # Display a green or red dot
    # (We handle "CORE Aggregate" vs "CORE" naming carefully.)
    # For simplicity, if "CORE Aggregate" was chosen, we treat it like "CORE"
    def green_dot():
        return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
    def red_dot():
        return "<span style='color: red; font-size: 20px;'>&#9679;</span>"

    # We'll unify "CORE Aggregate" vs "CORE" for display
    # if your main app uses "CORE Aggregate", just rename or handle it
    display_apis = []
    for ap in selected_apis:
        if ap.lower() in ["core", "core aggregate"]:
            # Check the boolean
            if core_ok is None:
                # Means not tested, but it's selected => show no key?
                status_html = f"{red_dot()} CORE: No API Key?"
            elif core_ok:
                status_html = f"{green_dot()} CORE: Verbindung OK"
            else:
                status_html = f"{red_dot()} CORE: Verbindung FAIL"
            display_apis.append(status_html)
        elif ap == "PubMed":
            if pubmed_ok is None:
                status_html = f"{red_dot()} PubMed: not tested"
            elif pubmed_ok:
                status_html = f"{green_dot()} PubMed: Verbindung OK"
            else:
                status_html = f"{red_dot()} PubMed: Verbindung FAIL"
            display_apis.append(status_html)
        elif ap == "Europe PMC":
            if epmc_ok is None:
                status_html = f"{red_dot()} Europe PMC: not tested"
            elif epmc_ok:
                status_html = f"{green_dot()} Europe PMC: Verbindung OK"
            else:
                status_html = f"{red_dot()} Europe PMC: Verbindung FAIL"
            display_apis.append(status_html)
        else:
            # For any other that we haven't coded checks for (OpenAlex, etc.)
            display_apis.append(f"{red_dot()} {ap}: keine Prüfung implementiert")

    st.markdown("<br>".join(display_apis), unsafe_allow_html=True)

    # -----------------------------
    # 7b) Checkboxes for standard keywords
    # -----------------------------
    st.subheader("Suchbegriffe auswählen")
    cb_geno = st.checkbox("Genotype", value=False)
    cb_pheno = st.checkbox("Phenotype", value=False)
    cb_snp = st.checkbox("SNP", value=False)

    # Additional user-supplied keywords
    st.subheader("Weitere Codewörter (optional)")
    user_keywords_str = st.text_input("Kommaseparierte Schlagwörter", "")

    selected_terms = []
    if cb_geno: selected_terms.append("genotype")
    if cb_pheno: selected_terms.append("phenotype")
    if cb_snp:   selected_terms.append("SNP")

    if user_keywords_str.strip():
        extra_kw_list = [w.strip() for w in user_keywords_str.split(",") if w.strip()]
        selected_terms.extend(extra_kw_list)

    if selected_terms:
        st.write("Aktuelle Suchbegriffe:", selected_terms)
    else:
        st.write("Noch keine Suchbegriffe ausgewählt/eingegeben.")

    # -----------------------------
    # 7c) ChatGPT-Filter on user-provided abstracts
    # -----------------------------
    st.subheader("ChatGPT-Filter für Abstracts")
    use_chatgpt = st.checkbox("ChatGPT-Filter aktivieren")

    abstract_input = st.text_area("Pro Zeile ein Abstract eingeben:")
    abstracts_list = [line.strip() for line in abstract_input.split("\n") if line.strip()]

    if use_chatgpt and st.button("Abstracts mit ChatGPT filtern"):
        if not selected_terms:
            st.warning("Bitte mindestens einen Suchbegriff wählen/eingeben!")
        else:
            filtered = filter_abstracts_with_chatgpt(abstracts_list, selected_terms)
            if not filtered:
                st.info("Keine Abstracts enthalten die Schlüsselwörter laut ChatGPT-Filter.")
            else:
                st.write("Gefilterte Abstracts (laut ChatGPT):")
                for f in filtered:
                    st.write("- ", f)

    # -----------------------------
    # 7d) Searching for Papers (using search_papers for demonstration)
    #     We’ll treat "CORE Aggregate" the same as "CORE".
    # -----------------------------
    st.subheader("Papersuche (100 pro ausgewählter API)")

    if st.button("Papers suchen"):
        if not selected_terms:
            st.warning("Keine Suchbegriffe ausgewählt. Bitte Checkboxen/Codewörter verwenden.")
            return

        query_str = " OR ".join(selected_terms)
        all_found = []

        # Because our function uses "CORE", let's unify name
        # main script has "CORE Aggregate" => rename to "CORE"
        # or handle it with an if condition:
        for active_api in selected_apis:
            # Some possible name normalizations:
            if active_api == "CORE Aggregate":
                api_name = "CORE"
            else:
                api_name = active_api

            # We only have search code for "PubMed", "Europe PMC", "CORE"
            # If the user selected e.g. "OpenAlex", we skip
            if api_name in ["PubMed", "Europe PMC", "CORE"]:
                found_papers = search_papers(api_name, query_str)
                all_found.extend(found_papers)
            else:
                st.info(f"No search function for {active_api} implemented yet.")

        st.write(f"Gefundene Papers gesamt: {len(all_found)}")
        if not all_found:
            return
        df = pd.DataFrame(all_found)
        st.session_state["papers_df"] = df
        st.write(df)

    # -----------------------------
    # 7e) Extra filter on the fetched table
    # -----------------------------
    st.subheader("Zusätzlicher Text-Filter (späte Filterung auf Ergebnistabelle)")
    extra_txt = st.text_input("Filterbegriff eingeben", "")
    if st.button("Filter Tabelle"):
        if "papers_df" not in st.session_state:
            st.warning("Keine Papers vorhanden. Bitte erst Suche durchführen.")
        else:
            df_pap = st.session_state["papers_df"]
            if df_pap.empty:
                st.info("Die Tabelle ist leer.")
            else:
                if extra_txt.strip():
                    df_filtered = df_pap[
                        df_pap.apply(lambda row: extra_txt.lower() in row.to_string().lower(), axis=1)
                    ]
                    st.write(f"Nach Filter '{extra_txt}' noch {len(df_filtered)} Papers:")
                    st.write(df_filtered)
                else:
                    st.info("Bitte einen Text eingeben, nach dem gefiltert werden soll.")

#############################################
# 8) (Example) Additional Modules
#############################################
def module_codewords_pubmed():
    st.header("Modul 3: Codewords & PubMed")
    st.write("Placeholder for the codewords_pubmed module...")

def module_select_remove():
    st.header("Modul 4: Paper Selection")
    st.write("Placeholder for the paper_select_remove module...")

def module_analysis():
    st.header("Modul 5: Analysis & Evaluation")
    st.write("Placeholder for the analysis module...")

def module_extended_topics():
    st.header("Modul 6: Extended Topics")
    st.write("Placeholder for the extended_topics module...")

#############################################
# 9) Top Green Bar with Multi-Select of APIs
#############################################
def top_api_selection():
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        /* Force sidebar buttons to be full width */
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

    # Top bar
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

    selected = st.multiselect(
        "Select APIs:",
        options,
        default=st.session_state["selected_apis"],
        key="top_api_select",
        label_visibility="collapsed"
    )
    st.session_state["selected_apis"] = selected

    st.markdown(
        f"""
        <div style="color: white; font-size: 16px; margin-top: 10px;">
            Currently selected: {", ".join(selected)}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

#############################################
# 10) Sidebar Navigation
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
# 11) Main Streamlit App
#############################################
def main():
    # Clear top space to not overlap the green bar
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
    
    # The top green bar (API selection)
    top_api_selection()
    
    # Add spacer so content starts below the green bar
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("API Connection Checker & Combined Results Demo")
    st.write("Each selected API can yield up to 100 results. E.g. with 2 APIs => 200 results total.")
    
    # Sidebar nav
    sidebar_module_navigation()

    # Basic search for combined results (PubMed / Europe PMC / CORE)
    st.header("Search & Combine Results from the Selected APIs")

    if "combined_results" not in st.session_state:
        st.session_state["combined_results"] = []
    if "selected_papers" not in st.session_state:
        st.session_state["selected_papers"] = []
    
    query = st.text_input("Enter a search query:", "")
    
    if st.button("Search (Combined)"):
        combined = []
        selected_apis = st.session_state["selected_apis"]
        
        if not query.strip():
            st.warning("Please enter a search query.")
        else:
            if "PubMed" in selected_apis:
                pubmed_res = search_pubmed(query)
                combined.extend(pubmed_res)
            if "Europe PMC" in selected_apis:
                epmc_res = search_europe_pmc(query)
                combined.extend(epmc_res)
            if "CORE Aggregate" in selected_apis:
                core_res = search_core_aggregate(query)
                combined.extend(core_res)
            
            # Additional APIs (OpenAlex, etc.) could be appended here.
            
            st.session_state["combined_results"] = combined
            st.write(f"Total results from selected APIs: {len(combined)}")
    
    # Display combined results
    if st.session_state["combined_results"]:
        st.subheader("All Combined Results (tiny font table)")

        # Make table font smaller
        st.markdown("""
        <style>
        table, thead, tbody, tr, td, th {
            font-size: 4px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.table(st.session_state["combined_results"])
        
        # Let user pick multiple to fetch abstracts
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
        
        selected_details = []
        for item in st.session_state["selected_papers"]:
            try:
                pmid = item.split("PMID: ")[1].rstrip(")")
            except IndexError:
                pmid = ""
            if pmid and pmid != "n/a":
                abstract_text = fetch_pubmed_abstract(pmid)
            else:
                abstract_text = "(No abstract / not from PubMed)"
            
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
    
    # Finally, check which module was chosen in the sidebar
    module = st.session_state.get("selected_module", "api_selection")
    if module == "api_selection":
        st.info("API Selection is at the top green bar.")
    elif module == "online_filter":
        module_online_filter()
    elif module == "codewords_pubmed":
        module_codewords_pubmed()
    elif module == "paper_selection":
        module_select_remove()
    elif module == "analysis":
        module_analysis()
    elif module == "extended_topics":
        module_extended_topics()
    
    st.write("Done. Up to 100 results per selected API, e.g. 2 APIs => 200, etc.")

if __name__ == '__main__':
    main()
