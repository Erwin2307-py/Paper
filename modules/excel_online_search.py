import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

# Optional: falls du ein eigenes Modul 'online_filter' verwendest:
# from modules.online_filter import module_online_filter

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")


################################################################################
# 1) Gemeinsame Funktionen & Klassen
################################################################################

# ==============================================================================
# CORE Aggregate API Class and Connection Check
# ==============================================================================
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


def check_core_aggregate_connection(api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF", timeout=15):
    try:
        core = CoreAPI(api_key)
        result = core.search_publications("test", limit=1)
        return "results" in result
    except Exception:
        return False


def search_core_aggregate(query, api_key="LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"):
    """Einfache Variante: Title/Year/Journal ohne Abstract."""
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


# ==============================================================================
# PubMed Connection Check + (Basis) Search
# ==============================================================================
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


def search_pubmed_simple(query):
    """Kurze Version: Sucht nur, ohne Abstract / Details."""
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
    """Holt den Abstract via efetch für eine gegebene PubMed-ID."""
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


# ==============================================================================
# Europe PMC Connection Check + (Basis) Search
# ==============================================================================
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


def search_europe_pmc_simple(query):
    """Kurze Version: Sucht nur, ohne erweiterte Details."""
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


# ==============================================================================
# OpenAlex API Communication
# ==============================================================================
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

def search_openalex_simple(query):
    """Kurze Version: Liest die rohen Daten, prüft nur, ob was zurückkommt."""
    search_params = {"search": query}
    return fetch_openalex_data("works", params=search_params)


# ==============================================================================
# Google Scholar (Basis) Test
# ==============================================================================
from scholarly import scholarly

class GoogleScholarSearch:
    def __init__(self):
        self.all_results = []

    def search_google_scholar(self, base_query):
        try:
            search_results = scholarly.search_pubs(base_query)
            # Nur 5 Abrufe als Test
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
        except Exception as e:
            st.error(f"Fehler bei der Google Scholar-Suche: {e}")


# ==============================================================================
# Semantic Scholar API Communication
# ==============================================================================
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


################################################################################
# 2) Neues Modul: "module_excel_online_search" (verbessert)
################################################################################

# ----------------------------- Hilfsfunktionen --------------------------------

def get_pubmed_details(pmid):
    """Holt Details über esummary + Abstract per efetch für eine PubMed-ID."""
    details = {}
    esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        r = requests.get(esummary_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("result", {}).get(pmid, {})
        details.update(data)
    except Exception as e:
        details["esummary_error"] = str(e)

    # Abstract via efetch
    details["Abstract"] = fetch_pubmed_abstract(pmid)
    return details


def search_pubmed(query, limit=100):
    """Sucht in PubMed per esearch, holt Metadaten (esummary) + Abstract (efetch)."""
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit}
    results = []
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return results

        # Metadaten via esummary
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        sum_data = r2.json().get("result", {})

        for pmid in idlist:
            info = sum_data.get(pmid, {})
            title = info.get("title", "N/A")
            pubdate = info.get("pubdate", "N/A")
            year = pubdate[:4] if pubdate and pubdate != "N/A" else "N/A"
            journal = info.get("fulljournalname", "N/A")
            doi = info.get("elocationid", "N/A")
            abstract = fetch_pubmed_abstract(pmid)

            results.append({
                "Source": "PubMed",
                "PubMed ID": pmid,
                "DOI": doi,
                "Title": title,
                "Year": year,
                "Publisher": journal,
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })
        return results
    except Exception as e:
        st.error(f"PubMed search error: {e}")
        return results


def search_europe_pmc(query, limit=100):
    """Sucht in Europe PMC per REST-API, inkl. Abstract."""
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": limit, "resultType": "core"}
    results = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "resultList" not in data or "result" not in data["resultList"]:
            return results

        for item in data["resultList"]["result"]:
            pmid = item.get("pmid", "N/A")
            title = item.get("title", "N/A")
            year = str(item.get("pubYear", "N/A"))
            journal = item.get("journalTitle", "N/A")
            doi = item.get("doi", "N/A")
            abstract = item.get("abstractText", "(No abstract available)")

            results.append({
                "Source": "Europe PMC",
                "PubMed ID": pmid,
                "DOI": doi,
                "Title": title,
                "Year": year,
                "Publisher": journal,
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })
        return results
    except Exception as e:
        st.error(f"Europe PMC search error: {e}")
        return results


def search_core_aggregate_detailed(query, limit=100):
    """Benutzt CORE-API (API-Key) und liefert Abstract mit zurück, falls vorhanden."""
    API_KEY = "LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {"q": query, "limit": limit}
    results = []
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for item in data.get("results", []):
            title = item.get("title", "N/A")
            year = str(item.get("yearPublished", "N/A"))
            publisher = item.get("publisher", "N/A")
            doi = item.get("doi", "N/A")
            abstract = item.get("abstract", "(No abstract available)")
            results.append({
                "Source": "CORE Aggregate",
                "PubMed ID": "N/A",
                "DOI": doi,
                "Title": title,
                "Year": year,
                "Publisher": publisher,
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })
        return results
    except Exception as e:
        st.error(f"CORE Aggregate search error: {e}")
        return results


def search_openalex(query, limit=100):
    """Sucht in OpenAlex (mit Abstract, sofern vorhanden)."""
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": limit}
    results = []
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for work in data.get("results", []):
            title = work.get("title", "N/A")
            year = str(work.get("publication_year", "N/A"))
            doi = work.get("doi", "N/A")
            journal = work.get("host_venue", {}).get("display_name", "N/A")
            abstract = work.get("abstract", "(No abstract available)")

            results.append({
                "Source": "OpenAlex",
                "PubMed ID": "N/A",
                "DOI": doi,
                "Title": title,
                "Year": year,
                "Publisher": journal,
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })
        return results
    except Exception as e:
        st.error(f"OpenAlex search error: {e}")
        return results


def search_google_scholar(query, limit=100):
    """Inoffizielles Google-Scholar-Paket 'scholarly'. Beschränkt auf `limit` Treffer."""
    from scholarly import scholarly
    results = []
    try:
        search_results = scholarly.search_pubs(query)
        count = 0
        while count < limit:
            try:
                result = next(search_results)
                title = result['bib'].get('title', "N/A")
                # Optional: Autoren oder Publikationsort
                year = result['bib'].get('pub_year', "N/A")
                doi = "N/A"
                abstract = result['bib'].get('abstract', "(No abstract available)")

                results.append({
                    "Source": "Google Scholar",
                    "PubMed ID": "N/A",
                    "DOI": doi,
                    "Title": title,
                    "Year": year,
                    "Publisher": "N/A",
                    "Population": "N/A",
                    "Cohorts": "N/A",
                    "Sample Size": "N/A",
                    "Abstract": abstract
                })
                count += 1
            except StopIteration:
                break
        return results
    except Exception as e:
        st.error(f"Google Scholar search error: {e}")
        return results


def search_semantic_scholar(query, limit=100):
    """Sucht in Semantic Scholar (max. `limit` Treffer)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    params = {"query": query, "limit": limit, "fields": "title,authors,year,abstract,doi,paperId"}
    results = []
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for paper in data.get("data", []):
            title = paper.get("title", "N/A")
            authors = ", ".join([a.get("name", "") for a in paper.get("authors", [])])
            year = str(paper.get("year", "N/A"))
            doi = paper.get("doi", "N/A")
            abstract = paper.get("abstract", "(No abstract available)")

            results.append({
                "Source": "Semantic Scholar",
                "PubMed ID": "N/A",
                "DOI": doi,
                "Title": title,
                "Year": year,
                "Publisher": "N/A",
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })
        return results
    except Exception as e:
        st.error(f"Semantic Scholar search error: {e}")
        return results


def create_excel_file(papers, query):
    """
    Erstellt eine Excel-Datei (BytesIO) mit:
      - Main-Sheet (Title, PubMed ID, Year, Publisher)
      - Detail-Sheets (alle verfügbaren Felder pro Paper).
    Falls es sich um PubMed-Paper handelt, werden mit get_pubmed_details()
    zusätzliche Daten geholt.
    """
    output = BytesIO()
    main_data = []
    details_dict = {}

    for paper in papers:
        main_data.append({
            "Title": paper.get("Title", "N/A"),
            "PubMed ID": paper.get("PubMed ID", "N/A"),
            "Year": paper.get("Year", "N/A"),
            "Publisher": paper.get("Publisher", "N/A")
        })

        # Falls PubMed: Hole zusätzliche Details (efetch + esummary)
        detail_info = paper.copy()
        if paper.get("Source") == "PubMed" and paper.get("PubMed ID") != "N/A":
            pmid = paper["PubMed ID"]
            pubmed_extra = get_pubmed_details(pmid)
            # Zusammenführen: Bevorzugt Details aus pubmed_extra
            for k, v in pubmed_extra.items():
                detail_info[k] = v

        # Dictionary => DataFrame (Key/Value)
        detail_df = pd.DataFrame(list(detail_info.items()), columns=["Field", "Value"])

        # Titel als Basis für den Sheet-Namen
        title = paper.get("Title", "Paper")

        # ---------------------------------------------------------
        # NEUE, VERBESSERTE LOGIK: Alle ungültigen Zeichen entfernen
        # ---------------------------------------------------------
        # Excel verbietet: \ / ? * [ ] : ' " < > | und max. 31 Zeichen
        sheet_name = re.sub(r'[\\/\?\*\[\]\:\'\"\<\>\|]', "", title)
        sheet_name = sheet_name[:31]  # auf max. 31 Zeichen kürzen
        if not sheet_name.strip():    # Falls jetzt leer oder nur Leerzeichen
            sheet_name = "Paper"

        # Prüfe, ob es den Namen bereits gibt (wir hängen ggf. Zähler an)
        orig_sheet_name = sheet_name
        counter = 2
        while sheet_name in details_dict:
            # Wieder kürzen, um zusammen mit Zähler nicht über 31 zu kommen
            new_name = f"{orig_sheet_name[:(31 - len(str(counter)) - 1)]}_{counter}"
            sheet_name = new_name
            counter += 1

        details_dict[sheet_name] = detail_df

    main_df = pd.DataFrame(main_data)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Main-Sheet
        main_df.to_excel(writer, index=False, sheet_name="Main")

        # Detail-Sheets
        for sheet, df in details_dict.items():
            df.to_excel(writer, index=False, sheet_name=sheet)

        writer.save()

    output.seek(0)
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{query}_{now}.xlsx"
    return output, file_name


def module_excel_online_search():
    """
    Zeigt im Streamlit-Interface Checkboxen für APIs, Codewörter-Feld,
    führt die Suche durch, zeigt Ergebnisse + Details und ermöglicht Excel-Export.
    """
    st.header("Online Suche & Excel-Erstellung")
    st.write("Für jede aktivierte API werden jeweils bis zu 100 Paper abgefragt.")
    
    # Definierte APIs – jede Funktion liefert bis zu 100 Paper
    apis = {
        "PubMed": search_pubmed,
        "Europe PMC": search_europe_pmc,
        "CORE Aggregate": search_core_aggregate_detailed,  # Detail-Version
        "OpenAlex": search_openalex,
        "Google Scholar": search_google_scholar,
        "Semantic Scholar": search_semantic_scholar
    }

    st.subheader("Wähle die APIs aus (Standard: PubMed aktiv):")
    selected_apis = [
        api for api in apis
        if st.checkbox(api, value=(api == "PubMed"))
    ]
    
    codewords_input = st.text_input("Codewörter (kommagetrennt, OR-Suche):", "")
    auto_wildcard = st.checkbox("Wildcard (*) automatisch anhängen, falls nicht vorhanden", value=False)
    
    if st.button("Suche starten"):
        if not codewords_input.strip():
            st.warning("Bitte gib mindestens ein Codewort ein!")
            return

        # Codewörter aufbereiten
        codewords = [cw.strip() for cw in codewords_input.split(",") if cw.strip()]
        if auto_wildcard:
            codewords = [cw if "*" in cw else cw + "*" for cw in codewords]
        query = " OR ".join(codewords)

        st.write("Suchanfrage:", query)
        
        all_results = []
        for api in selected_apis:
            st.write(f"Suche in {api} …")
            search_func = apis[api]
            results = search_func(query, limit=100)
            st.write(f"{len(results)} Paper gefunden in {api}.")
            all_results.extend(results)

        if all_results:
            df = pd.DataFrame(all_results)
            st.subheader("Gefundene Paper (Kompaktansicht)")
            st.dataframe(df)
            st.session_state["excel_results"] = all_results
            st.session_state["search_query"] = query
        else:
            st.info("Keine Paper gefunden.")
    
    # Paper-Details anzeigen
    if "excel_results" in st.session_state and st.session_state["excel_results"]:
        paper_titles = [paper.get("Title", "N/A") for paper in st.session_state["excel_results"]]
        if paper_titles:
            selected_title = st.selectbox(
                "Wähle ein Paper, um den Abstract und weitere Details anzuzeigen:",
                ["(Keine Auswahl)"] + paper_titles
            )
            if selected_title != "(Keine Auswahl)":
                selected_paper = next(
                    (p for p in st.session_state["excel_results"] if p.get("Title") == selected_title),
                    None
                )
                if selected_paper:
                    with st.expander("Abstract & Details anzeigen"):
                        st.subheader(selected_title)
                        st.markdown("**Abstract:**")
                        st.write(selected_paper.get("Abstract", "Kein Abstract vorhanden."))
                        st.markdown("**Alle Informationen:**")
                        st.write(selected_paper)
    
    # Excel-Download
    if "excel_results" in st.session_state and st.session_state["excel_results"]:
        if st.button("Excel-Datei herunterladen"):
            query = st.session_state.get("search_query", "Results")
            excel_file, file_name = create_excel_file(st.session_state["excel_results"], query)
            st.download_button(
                label="Download Excel",
                data=excel_file,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


################################################################################
# 3) Restliche Module + Seiten (Pages)
################################################################################

def module_paperqa2():
    st.subheader("PaperQA2 Module")
    st.write("Dies ist das PaperQA2 Modul. Hier kannst du weitere Einstellungen und Funktionen für PaperQA2 implementieren.")
    # Beispielhafte Funktionalität: Eingabe einer Frage und Anzeige einer Dummy-Antwort
    question = st.text_input("Bitte gib deine Frage ein:")
    if st.button("Frage absenden"):
        st.write("Antwort: Dies ist eine Dummy-Antwort auf die Frage:", question)


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
    chosen_apis = [
        api for api in all_apis
        if st.checkbox(api, value=(api in st.session_state["selected_apis"]))
    ]
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
            test_scholar = GoogleScholarSearch()
            test_scholar.search_google_scholar("test")
            msgs.append("Google Scholar: OK")
        except Exception as e:
            msgs.append(f"Google Scholar: FAIL ({str(e)})")

    if "Semantic Scholar" in chosen_apis:
        if check_semantic_scholar_connection():
            msgs.append("Semantic Scholar: OK")
        else:
            msgs.append("Semantic Scholar: FAIL")

    if msgs:
        for m in msgs:
            st.write("- ", m)
    else:
        st.write("No APIs selected or no checks performed.")

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here.")
    # Falls dein Modul hier importiert werden soll:
    # module_online_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    # Hier importieren und aufrufen wir das separate Modul
    # from modules.codewords_pubmed import module_codewords_pubmed
    # module_codewords_pubmed()
    st.write("(Platzhalter für 'modules.codewords_pubmed')")

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


def page_paperqa2():
    st.title("PaperQA2")
    module_paperqa2()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


def page_excel_online_search():
    st.title("Excel Online Search")
    module_excel_online_search()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"


################################################################################
# 4) Sidebar Module Navigation & Main
################################################################################

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
        "7) PaperQA2": page_paperqa2,
        "8) Excel Online Search": page_excel_online_search
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]


def main():
    # Kleines CSS / Layout-Tuning
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
