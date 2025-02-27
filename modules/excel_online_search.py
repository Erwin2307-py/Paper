import streamlit as st
import pandas as pd
import requests
import re
import datetime
from io import BytesIO
import xml.etree.ElementTree as ET

#############################################
# Helper-Funktionen für PubMed
#############################################
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

def get_pubmed_details(pmid):
    """Ruft alle Details via esummary und efetch (Abstract) für eine PubMed-ID ab."""
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

#############################################
# Suchfunktionen für die verschiedenen APIs (Limit=100)
#############################################
def search_pubmed(query, limit=100):
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
        # Abfrage der Metadaten via esummary
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

def search_core_aggregate(query, limit=100):
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
    from scholarly import scholarly
    results = []
    try:
        search_results = scholarly.search_pubs(query)
        count = 0
        while count < limit:
            try:
                result = next(search_results)
                title = result['bib'].get('title', "N/A")
                authors = result['bib'].get('author', "N/A")
                year = result['bib'].get('pub_year', "N/A")
                doi = "N/A"
                url_article = result.get('url_scholarbib', "N/A")
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

#############################################
# Excel-Erstellung: Main-Sheet + Detail-Sheets
#############################################
def create_excel_file(papers, query):
    output = BytesIO()
    main_data = []
    details_dict = {}
    for paper in papers:
        # Für den Main-Sheet: Nur Name (Title), PubMed ID, Year, Publisher
        main_data.append({
            "Title": paper.get("Title", "N/A"),
            "PubMed ID": paper.get("PubMed ID", "N/A"),
            "Year": paper.get("Year", "N/A"),
            "Publisher": paper.get("Publisher", "N/A")
        })
        # Für Detail-Sheets: Falls PubMed, hole ggf. detaillierte Daten über efetch/esummary
        detail_info = paper.copy()
        if paper.get("Source") == "PubMed" and paper.get("PubMed ID") != "N/A":
            pmid = paper.get("PubMed ID")
            detail_info = get_pubmed_details(pmid)
            # Ergänze ggf. Basisinformationen, falls nicht vorhanden:
            detail_info.setdefault("Title", paper.get("Title", "N/A"))
            detail_info.setdefault("PubMed ID", pmid)
            detail_info.setdefault("Year", paper.get("Year", "N/A"))
            detail_info.setdefault("Publisher", paper.get("Publisher", "N/A"))
        # Erstelle DataFrame aus allen Key/Value-Paaren
        detail_df = pd.DataFrame(list(detail_info.items()), columns=["Field", "Value"])
        title = paper.get("Title", "Paper")
        # Bereinige Sheet-Namen: max. 31 Zeichen, ungültige Zeichen entfernen
        sheet_name = re.sub(r'[\\/*?:"<>|]', "", title)[:31]
        # Eindeutiger Sheet-Name
        if sheet_name in details_dict:
            counter = 2
            new_sheet = f"{sheet_name}_{counter}"
            while new_sheet in details_dict:
                counter += 1
                new_sheet = f"{sheet_name}_{counter}"
            sheet_name = new_sheet
        details_dict[sheet_name] = detail_df

    main_df = pd.DataFrame(main_data)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        main_df.to_excel(writer, index=False, sheet_name="Main")
        for sheet, df in details_dict.items():
            df.to_excel(writer, index=False, sheet_name=sheet)
        writer.save()
    output.seek(0)
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{query}_{now}.xlsx"
    return output, file_name

#############################################
# Hauptfunktion des Moduls
#############################################
def module_excel_online_search():
    st.header("Online Suche & Excel-Erstellung")
    st.write("Für jede aktivierte API werden jeweils bis zu 100 Paper abgefragt.")
    
    # Definierte APIs – jede Funktion liefert bis zu 100 Paper
    apis = {
        "PubMed": search_pubmed,
        "Europe PMC": search_europe_pmc,
        "CORE Aggregate": search_core_aggregate,
        "OpenAlex": search_openalex,
        "Google Scholar": search_google_scholar,
        "Semantic Scholar": search_semantic_scholar
    }
    st.subheader("Wähle die APIs aus:")
    # Standardmäßig ist hier PubMed aktiviert
    selected_apis = [api for api in apis if st.checkbox(api, value=(api=="PubMed"))]
    
    codewords_input = st.text_input("Codewörter (kommagetrennt, OR-Suche):", "")
    auto_wildcard = st.checkbox("Wildcard (*) automatisch anhängen, falls nicht vorhanden", value=False)
    
    if st.button("Suche starten"):
        if not codewords_input.strip():
            st.warning("Bitte gib mindestens ein Codewort ein!")
            return
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
            st.subheader("Gefundene Paper")
            st.dataframe(df)
            st.session_state["excel_results"] = all_results
            st.session_state["search_query"] = query
        else:
            st.info("Keine Paper gefunden.")
    
    # Anzeige des Abstracts und aller Details für ein ausgewähltes Paper
    if "excel_results" in st.session_state and st.session_state["excel_results"]:
        paper_titles = [paper.get("Title", "N/A") for paper in st.session_state["excel_results"]]
        selected_title = st.selectbox("Wähle ein Paper, um den Abstract und weitere Details anzuzeigen:", paper_titles)
        if selected_title:
            selected_paper = next((paper for paper in st.session_state["excel_results"] if paper.get("Title") == selected_title), None)
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
