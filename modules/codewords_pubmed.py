import streamlit as st
import pandas as pd
import requests
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

def module_codewords_pubmed():
    st.header("Codewords & PubMed")

    # API-Verbindung prüfen und anzeigen
    st.subheader("API Status")
    pubmed_status = "OK" if check_pubmed_connection() else "FAIL"
    st.write("PubMed API:", pubmed_status)
    # Hier könnten weitere API-Checks ergänzt werden

    # Anzeige der aktuell gesetzten Online-Filter (sofern im Session-State gespeichert)
    st.subheader("Aktuell gesetzte Online Filter")
    if "online_filter_terms" in st.session_state:
        st.write("Online Filter Codewörter:", st.session_state["online_filter_terms"])
    else:
        st.write("Keine Online Filter Codewörter gesetzt.")

    # Eingabe der Codewörter für die Suche
    st.subheader("Codewörter für die Suche eingeben")
    codewords_input = st.text_input("Codewörter (kommagetrennt, Wildcard (*) möglich):", "")

    # Option, Wildcard automatisch anzuhängen, falls nicht vorhanden
    auto_wildcard = st.checkbox("Automatisch Wildcard (*) anhängen, falls nicht vorhanden", value=False)

    if st.button("Suche durchführen"):
        if not codewords_input.strip():
            st.warning("Bitte geben Sie mindestens ein Codewort ein!")
        else:
            # Codewörter parsen und ggf. Wildcard ergänzen
            codewords_list = [cw.strip() for cw in codewords_input.split(",") if cw.strip()]
            if auto_wildcard:
                codewords_list = [cw if "*" in cw else cw + "*" for cw in codewords_list]
            # Erstelle Suchanfrage: Verknüpfe die Codewörter mit OR
            query = " OR ".join(codewords_list)
            st.write("Suchanfrage:", query)

            # Suche über PubMed (mittels der Funktion aus online_filter)
            papers = search_papers("PubMed", query)
            if papers:
                st.write("Gefundene Papers:")
                df = pd.DataFrame(papers)
                st.write(df)
                st.session_state["papers_df"] = df
            else:
                st.write("Keine Papers gefunden.")

