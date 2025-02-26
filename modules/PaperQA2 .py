import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
from scholarly import scholarly
from modules.online_filter import module_online_filter

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

def check_core_aggregate_connection(api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF", timeout=15):
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False

def search_core_aggregate(query, api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"):
    if not api_key:
        return []
    try:
        core = CoreAPI(api_key)
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
# OpenAlex API Communication
#############################################
BASE_URL = "https://api.openalex.org"

def fetch_openalex_data(entity_type, entity_id=None, params=None):
    url = f"{BASE_URL}/{entity_type}"
    if entity_id:
        url += f"/{entity_id}"
    
    if params is None:
        params = {}
    params["mailto"] = "your_email@example.com"  # Ersetze durch deine E-Mail-Adresse
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Fehler: {response.status_code} - {response.text}")
        return None

def search_openalex(query):
    search_params = {"search": query}
    return fetch_openalex_data("works", params=search_params)

#############################################
# Google Scholar API Communication
#############################################
class GoogleScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_google_scholar(self, base_query):
        try:
            search_results = scholarly.search_pubs(base_query)
            for _ in range(5):
                result = next(search_results)
                title = result['bib'].get('title', "n/a")
                authors = result['bib'].get('author', "n/a")
                year = result['bib'].get('pub_year', "n/a")
                url_article = result.get('url_scholarbib', "n/a")
                abstract_text = result['bib'].get('abstract', "")
                self.all_results.append({
                    "Source": "Google Scholar",
                    "Title": title,
                    "Authors/Description": authors,
                    "Journal/Organism": "n/a",
                    "Year": year,
                    "PMID": "n/a",
                    "DOI": "n/a",
                    "URL": url_article,
                    "Abstract": abstract_text
                })
            for idx, entry in enumerate(self.all_results, start=1):
                print(f"{idx}. Titel: {entry['Title']}")
                print(f"   Autoren: {entry['Authors/Description']}")
                print(f"   Jahr: {entry['Year']}")
                print(f"   URL: {entry['URL']}")
                print(f"   Abstract: {entry['Abstract']}\n")
        except Exception as e:
            st.error(f"Fehler bei der Google Scholar-Suche: {e}")

#############################################
# Semantic Scholar API Communication
#############################################
class SemanticScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_semantic_scholar(self, base_query):
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
            params = {"query": base_query, "limit": 5, "fields": "title,authors,year,abstract,doi,paperId"}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            for paper in data.get("data", []):
                title = paper.get("title", "n/a")
                authors = ", ".join([author.get("name", "") for author in paper.get("authors", [])])
                year = paper.get("year", "n/a")
                doi = paper.get("doi", "n/a")
                paper_id = paper.get("paperId", "")
                abstract_text = paper.get("abstract", "")
                url_article = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "n/a"
                self.all_results.append({
                    "Source": "Semantic Scholar",
                    "Title": title,
                    "Authors/Description": authors,
                    "Journal/Organism": "n/a",
                    "Year": year,
                    "PMID": "n/a",
                    "DOI": doi,
                    "URL": url_article,
                    "Abstract": abstract_text
                })
        except Exception as e:
            st.error(f"Semantic Scholar: {e}")

def check_semantic_scholar_connection(timeout=10):
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": "test", "limit": 1, "fields": "title"}
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.status_code == 200
    except Exception:
        return False

#############################################
# Excel-Hilfsfunktion
#############################################
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

def page_api_selection():
    st.title("API Selection & Connection Status")
    st.write("Auf dieser Seite kannst du die zu verwendenden APIs wählen und den Verbindungsstatus prüfen.")

    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]

    chosen_apis = [api for api in all_apis if st.checkbox(api, value=api in st.session_state["selected_apis"])]
    st.session_state["selected_apis"] = chosen_apis

    st.write("Currently selected APIs:", chosen_apis)

    st.subheader("Connection Tests")
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
        core_key = "LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"
        if core_key and check_core_aggregate_connection(core_key):
            msgs.append("CORE: OK")
        else:
            msgs.append("CORE: FAIL (No valid key or no connection)")
    if "OpenAlex" in chosen_apis:
        openalex_test = fetch_openalex_data("works", "W2741809807")
        if openalex_test:
            msgs.append("OpenAlex: OK")
        else:
            msgs.append("OpenAlex: FAIL")
    if "Google Scholar" in chosen_apis:
        try:
            GoogleScholarSearch().search_google_scholar("test")
            msgs.append("Google Scholar: OK")
        except Exception as e:
            msgs.append(f"Google Scholar: FAIL ({str(e)})")
    if "Semantic Scholar" in chosen_apis:
        if check_semantic_scholar_connection():
            msgs.append("Semantic Scholar: OK")
        else:
            msgs.append("Semantic Scholar: FAIL")

    for m in msgs:
        st.write("- ", m)

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here.")
    module_online_filter()
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

# Neues Modul: PaperQA2 mit lokaler Paper-Auswahl, Analyse und Frage-Antwort-Funktion
def page_paperqa2():
    st.title("PaperQA2 - Lokale Paper-Auswahl, Analyse & Fragen")
    st.write("Wähle ein lokales Paper aus, lasse es analysieren und stelle anschließend Fragen dazu.")

    # Zuerst: Button, um den File-Uploader einzublenden
    if "paper_file" not in st.session_state:
        if st.button("Paper auswählen"):
            st.session_state["show_uploader"] = True

    # Falls der Uploader angezeigt werden soll
    if st.session_state.get("show_uploader", False):
        uploaded_file = st.file_uploader("Wähle eine lokale Paper-Datei aus", type=["pdf", "txt"])
        if uploaded_file is not None:
            st.session_state["paper_file"] = uploaded_file
            st.write("Hochgeladene Datei:", uploaded_file.name)
            # Uploader wieder ausblenden
            st.session_state["show_uploader"] = False

    # Falls bereits ein Paper ausgewählt wurde
    if "paper_file" in st.session_state:
        st.write("Ausgewähltes Paper:", st.session_state["paper_file"].name)
        if st.button("Paper analysieren"):
            # Hier wird die Dummy-Analyse ausgeführt – ersetze dies durch deine Analyse-Funktion
            analysis_result = "Dies ist eine Dummy-Analyse des Papers."
            st.session_state["paper_analysis"] = analysis_result
            st.success("Paper wurde analysiert.")

        # Falls bereits eine Analyse vorliegt, kann der Benutzer Fragen stellen.
        if "paper_analysis" in st.session_state:
            st.subheader("Frage zum Paper stellen")
            user_question = st.text_input("Gib deine Frage ein:")
            if st.button("Frage absenden"):
                # Dummy-Antwort – ersetze dies durch deine Frage-Antwort-Logik
                answer = f"Dummy-Antwort auf deine Frage: {user_question}"
                st.write(answer)

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

#############################################
# Sidebar Module Navigation
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "1) API Selection": page_api_selection,
        "2) Online Filter": page_online_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics,
        "7) PaperQA2": page_paperqa2
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]

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
    page_fn = sidebar_module_navigation()
    page_fn()

if __name__ == '__main__':
    main()
