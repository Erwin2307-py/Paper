"""
excel_search_module.py

Enthält das Modul "module_excel_online_search()", welches:
- Codewörter-Eingabe + APIs-Auswahl in Streamlit ermöglicht,
- pro ausgewählter API bis zu 100 Paper abfragt,
- die Ergebnisse im DataFrame anzeigt,
- pro Paper in einem eigenen Excel-Sheet alle Details speichert,
- ein Haupt-Sheet ("Main") erstellt, das eine kompakte Übersicht enthält
  (z.B. Titel, PubMedID, DOI, Jahr, Publisher, Population, Cohorts, Sample Size).
"""

import re
import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import streamlit as st

###############################################################################
# Hilfsfunktionen für PubMed
###############################################################################
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
    """Holt Details über esummary und Abstract per efetch für eine PubMed-ID."""
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

    # Abstract
    details["Abstract"] = fetch_pubmed_abstract(pmid)
    return details

###############################################################################
# API-spezifische Suchfunktionen
###############################################################################
def search_pubmed(query, limit=100):
    """
    Sucht in PubMed per esearch -> ermittelt IDs -> 
    holt Metadaten via esummary -> holt Abstract via efetch.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    esearch_url = base_url + "esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit}
    results = []

    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return results

        esummary_url = base_url + "esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        r2 = requests.get(esummary_url, params=sum_params, timeout=10)
        r2.raise_for_status()
        sum_data = r2.json().get("result", {})

        for pmid in idlist:
            info = sum_data.get(pmid, {})
            title = info.get("title", "N/A")
            pubdate = info.get("pubdate", "N/A")
            year = pubdate[:4] if pubdate else "N/A"
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
                # Zusätzliche Felder, falls vorhanden:
                "Population": "N/A",
                "Cohorts": "N/A",
                "Sample Size": "N/A",
                "Abstract": abstract
            })

        return results

    except Exception as e:
        st.error(f"[PubMed] Fehler: {e}")
        return results


def search_europe_pmc(query, limit=100):
    """
    Sucht in Europe PMC nach Ergebnissen inkl. Abstract (falls vorhanden).
    """
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
        st.error(f"[Europe PMC] Fehler: {e}")
        return results


def search_core_aggregate_detailed(query, limit=100):
    """
    Benutzt CORE-API (API-Key) und liefert Abstract mit zurück, falls vorhanden.
    """
    API_KEY = "LmAMxdYnK6SDJsPRQCpGgwN7f5yTUBHF"  # Dein CORE-API-Key
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
        st.error(f"[CORE] Fehler: {e}")
        return results


def search_openalex(query, limit=100):
    """
    Sucht in OpenAlex (mit Abstract, sofern vorhanden).
    """
    base_url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": limit}
    results = []

    try:
        r = requests.get(base_url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for work in data.get("results", []):
            title = work.get("title", "N/A")
            year = str(work.get("publication_year", "N/A"))
            doi = work.get("doi", "N/A")
            publisher = work.get("host_venue", {}).get("display_name", "N/A")
            abstract = work.get("abstract", "(No abstract available)")

            results.append({
                "Source": "OpenAlex",
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
        st.error(f"[OpenAlex] Fehler: {e}")
        return results


def search_google_scholar(query, limit=100):
    """
    Nutzt das inoffizielle Google-Scholar-Paket "scholarly"
    und liefert bis zu `limit` Ergebnisse.
    """
    from scholarly import scholarly
    results = []
    try:
        search_results = scholarly.search_pubs(query)
        count = 0
        while count < limit:
            try:
                paper = next(search_results)
                title = paper['bib'].get('title', "N/A")
                year = paper['bib'].get('pub_year', "N/A")
                doi = "N/A"
                abstract = paper['bib'].get('abstract', "(No abstract available)")

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
        st.error(f"[Google Scholar] Fehler: {e}")
        return results


def search_semantic_scholar(query, limit=100):
    """
    Sucht in Semantic Scholar (Graph-API),
    holt Titel, Autoren, Jahr, Abstract, DOI etc.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,abstract,doi,paperId"
    }
    results = []

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for paper in data.get("data", []):
            title = paper.get("title", "N/A")
            authors_list = paper.get("authors", [])
            authors_str = ", ".join(a.get("name", "") for a in authors_list)
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
        st.error(f"[Semantic Scholar] Fehler: {e}")
        return results


###############################################################################
# Excel-Erstellung
###############################################################################
def create_excel_file(papers, query):
    """
    Erstellt eine Excel-Datei (BytesIO) mit:
      1) Einem "Main"-Sheet, das pro Paper folgende Spalten hat:
         - Title, PubMed ID, DOI, Year, Publisher, Population, Cohorts, Sample Size
      2) Für jedes Paper ein eigenes Sheet, in dem alle Felder (Key/Value) stehen.

    Der Dateiname enthält den Suchbegriff sowie Datum+Uhrzeit:
      f"{query}_{YYYY-MM-DD_HH-MM-SS}.xlsx"
    """
    output = BytesIO()

    # Main-Sheet-Daten vorbereiten
    main_data = []
    details_dict = {}

    for paper in papers:
        # -> "Main"-Sheet: Nur best. Felder (falls nicht vorhanden -> "N/A")
        main_data.append({
            "Title": paper.get("Title", "N/A"),
            "PubMed ID": paper.get("PubMed ID", "N/A"),
            "DOI": paper.get("DOI", "N/A"),
            "Year": paper.get("Year", "N/A"),
            "Publisher": paper.get("Publisher", "N/A"),
            "Population": paper.get("Population", "N/A"),
            "Cohorts": paper.get("Cohorts", "N/A"),
            "Sample Size": paper.get("Sample Size", "N/A"),
        })

        # -> Detail-Sheet: Alle Felder
        detail_info = dict(paper)
        # Falls es ein PubMed-Paper ist, könnte man hier get_pubmed_details() erneut abrufen,
        # wenn man *noch* mehr Felder im Detailsheet haben möchte. (Bereits im search_pubmed enthalten.)
        detail_items = list(detail_info.items())  # [(key, value), (key, value), ...]
        detail_df = pd.DataFrame(detail_items, columns=["Field", "Value"])

        # Blattname = abgeleiteter Titel, bereinigen (Excel max. 31 Zeichen, verbotene Zeichen weg)
        raw_title = paper.get("Title", "Paper") or "Paper"
        sheet_name = re.sub(r'[\\/\?\*\[\]\:\'\"\<\>\|]', "", raw_title)
        sheet_name = sheet_name[:31].strip()
        if not sheet_name:
            sheet_name = "Paper"

        # Falls doppelte Blattnamen: anfügen von "_2", "_3", ...
        base_name = sheet_name
        counter = 2
        while sheet_name in details_dict:
            # Platz für Suffix
            suffix = f"_{counter}"
            max_len = 31 - len(suffix)
            sheet_name = (base_name[:max_len] + suffix).strip()
            counter += 1

        details_dict[sheet_name] = detail_df

    # Main-Sheet in DataFrame
    main_df = pd.DataFrame(main_data)

    # Excel erstellen
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Hauptsheet
        main_df.to_excel(writer, sheet_name="Main", index=False)

        # Detail-Sheets
        for s_name, df_details in details_dict.items():
            df_details.to_excel(writer, sheet_name=s_name, index=False)

        writer.save()

    output.seek(0)
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{query}_{now}.xlsx"
    return output, file_name

###############################################################################
# Das eigentliche Modul
###############################################################################
def module_excel_online_search():
    """
    Modul-Funktion, die Folgendes in Streamlit tut:
      1) APIs per Checkbox auswählen
      2) Codewörter-Eingabe (kommagetrennt, OR-Verknüpfung)
      3) Optional: Wildcard (*)
      4) Für jede aktive API bis zu 100 Paper abfragen
      5) Ergebnisse anzeigen
      6) Detailansicht pro Paper
      7) Excel-Download-Button (Erstellt 1 Main-Sheet, pro Paper 1 Detail-Sheet)
    """
    st.subheader("Online Suche & Excel-Erstellung (Modul)")

    # Verfügbare APIs
    apis = {
        "PubMed": search_pubmed,
        "Europe PMC": search_europe_pmc,
        "CORE Aggregate": search_core_aggregate_detailed,
        "OpenAlex": search_openalex,
        "Google Scholar": search_google_scholar,
        "Semantic Scholar": search_semantic_scholar,
    }

    st.write("Wähle die APIs, in denen gesucht werden soll:")
    selected_apis = [api for api in apis if st.checkbox(api, value=(api == "PubMed"))]

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

        query_str = " OR ".join(codewords)
        st.write(f"**Suchanfrage:** {query_str}")

        all_results = []
        for api in selected_apis:
            st.write(f"### Suche in {api}...")
            search_func = apis[api]
            try:
                found = search_func(query_str, limit=100)
            except Exception as err:
                st.error(f"{api}: {err}")
                found = []
            st.write(f"{len(found)} Paper gefunden in {api}.")
            all_results.extend(found)

        if all_results:
            df = pd.DataFrame(all_results)
            st.subheader("Gefundene Paper")
            st.dataframe(df)
            st.session_state["excel_results"] = all_results
            st.session_state["search_query"] = query_str
        else:
            st.warning("Keine Paper gefunden.")

    # Detailansicht
    if "excel_results" in st.session_state and st.session_state["excel_results"]:
        papers = st.session_state["excel_results"]
        titles = [p.get("Title", "N/A") for p in papers]
        selected_title = st.selectbox(
            "Wähle ein Paper für Detailansicht:",
            ["(Keine Auswahl)"] + titles
        )
        if selected_title and selected_title != "(Keine Auswahl)":
            chosen = next((p for p in papers if p.get("Title") == selected_title), None)
            if chosen:
                with st.expander("Details & Abstract"):
                    st.write(f"**Titel:** {selected_title}")
                    st.write(f"**Abstract:** {chosen.get('Abstract', '(No abstract)')}")
                    st.write("**Alle Felder:**")
                    st.json(chosen)

    # Excel-Download
    if "excel_results" in st.session_state and st.session_state["excel_results"]:
        if st.button("Excel-Datei herunterladen"):
            query = st.session_state.get("search_query", "Results")
            excel_bytes, filename = create_excel_file(st.session_state["excel_results"], query)
            st.download_button(
                "Download Excel",
                data=excel_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

