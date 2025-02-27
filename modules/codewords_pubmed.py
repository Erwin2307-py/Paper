import streamlit as st
import pandas as pd
import requests
import re
from io import BytesIO
from modules.online_filter import search_papers

def check_pubmed_connection(timeout=10):
    """Überprüft, ob die PubMed-API erreichbar ist."""
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def fetch_pubmed_abstract(pmid):
    """
    Holt den Abstract für eine gegebene PubMed-ID über efetch.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        import xml.etree.ElementTree as ET
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

def get_paper_details(pmid):
    """
    Holt detaillierte Informationen zu einem Paper:
      - ESummary liefert diverse Metadaten (z. B. Titel, Publikationsdatum, Herausgeber, DOI etc.)
      - EFetch liefert den Abstract.
    """
    esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        r = requests.get(esummary_url, params=params, timeout=10)
        r.raise_for_status()
        summary_json = r.json()
        details = summary_json.get("result", {}).get(pmid, {})
    except Exception as e:
        details = {}
    # Abstract über EFetch abrufen
    abstract = fetch_pubmed_abstract(pmid)
    details["Abstract"] = abstract
    return details

def create_excel_file(papers):
    """
    Erstellt ein Excel-Dokument mit:
      - einem Hauptsheet ("Main"), das pro Paper die Felder enthält:
        PubMed ID, DOI, Title, Year, Publisher, Population, Cohorts, Sample Size
      - für jedes Paper ein zusätzliches Sheet (benannt nach dem (bereinigten) Paper-Titel),
        das alle über ESummary und EFetch erhaltenen Informationen als Feld/Value-Tabelle enthält.
    """
    output = BytesIO()
    main_data = []
    details_dict = {}
    
    # Für jedes Paper werden die Detailinformationen abgerufen
    for paper in papers:
        pmid = paper.get("PubMed ID", "")
        details = get_paper_details(pmid)
        # Hauptinformationen (falls die Felder in den Details nicht vorhanden sind, wird der ursprüngliche Wert genutzt)
        title = details.get("title", paper.get("Title", "N/A"))
        doi = details.get("doi", details.get("elocationid", "N/A"))
        pubdate = details.get("pubdate", "N/A")
        year = pubdate[:4] if pubdate and pubdate != "N/A" else paper.get("Year", "N/A")
        publisher = details.get("fulljournalname", paper.get("Publisher", "N/A"))
        # Zusätzliche Felder (Population, Cohorts, Sample Size) – sofern nicht vorhanden, "N/A"
        population = details.get("population", "N/A")
        cohorts = details.get("cohorts", "N/A")
        sample_size = details.get("sample_size", "N/A")
        
        main_data.append({
            "PubMed ID": pmid,
            "DOI": doi,
            "Title": title,
            "Year": year,
            "Publisher": publisher,
            "Population": population,
            "Cohorts": cohorts,
            "Sample Size": sample_size
        })
        
        # Detail-Sheet: Alle Informationen aus details in einer Tabelle (Feld/Value)
        detail_items = list(details.items())
        detail_df = pd.DataFrame(detail_items, columns=["Field", "Value"])
        
        # Erzeuge einen gültigen Sheet-Namen aus dem Titel (max. 31 Zeichen, keine ungültigen Zeichen)
        sheet_name = re.sub(r'[:\\/*?\[\]]', '', title)
        if len(sheet_name) > 31:
            sheet_name = sheet_name[:31]
        details_dict[sheet_name] = detail_df

    main_df = pd.DataFrame(main_data)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        main_df.to_excel(writer, index=False, sheet_name="Main")
        for sheet, df in details_dict.items():
            df.to_excel(writer, index=False, sheet_name=sheet)
        writer.save()
    output.seek(0)
    return output

def module_codewords_pubmed():
    st.header("Codewords & PubMed")
    
    # API-Status anzeigen
    st.subheader("API Status")
    pubmed_status = "OK" if check_pubmed_connection() else "FAIL"
    st.write("PubMed API:", pubmed_status)
    
    # Anzeige aktuell gesetzter Online Filter (falls im Session-State gesetzt)
    st.subheader("Aktuell gesetzte Online Filter")
    if "online_filter_terms" in st.session_state:
        st.write("Online Filter Codewörter:", st.session_state["online_filter_terms"])
    else:
        st.write("Keine Online Filter Codewörter gesetzt.")
    
    # Eingabe der Codewörter für die Suche
    st.subheader("Codewörter für die Suche eingeben")
    codewords_input = st.text_input("Codewörter (kommagetrennt, Wildcard (*) möglich):", "")
    auto_wildcard = st.checkbox("Automatisch Wildcard (*) anhängen, falls nicht vorhanden", value=False)
    
    if st.button("Suche durchführen"):
        if not codewords_input.strip():
            st.warning("Bitte geben Sie mindestens ein Codewort ein!")
        else:
            codewords_list = [cw.strip() for cw in codewords_input.split(",") if cw.strip()]
            if auto_wildcard:
                codewords_list = [cw if "*" in cw else cw + "*" for cw in codewords_list]
            query = " OR ".join(codewords_list)
            st.write("Suchanfrage:", query)
            # Suche über PubMed – maximal 100 Paper (search_papers in online_filter nutzt retmax=100)
            papers = search_papers("PubMed", query)
            if papers:
                st.write("Gefundene Papers:")
                df = pd.DataFrame(papers)
                st.write(df)
                st.session_state["papers_df"] = df
            else:
                st.write("Keine Papers gefunden.")
    
    # Excel-Download anbieten, sofern Paper vorhanden sind
    if "papers_df" in st.session_state and not st.session_state["papers_df"].empty:
        if st.button("Excel herunterladen"):
            # Konvertiere die im Session-State gespeicherten Paper in eine Liste von Dictionaries
            papers_list = st.session_state["papers_df"].to_dict("records")
            excel_file = create_excel_file(papers_list)
            st.download_button(
                label="Download Excel",
                data=excel_file,
                file_name="pubmed_papers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
