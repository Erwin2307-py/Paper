import streamlit as st
import requests

def module_codewords_pubmed():
    st.header("Modul 3: Codewörter + PubMed-Suche")

    # Codewörter
    codewords = st.text_input("Codewörter (kommasepariert)", "genotype,snp")

    # Klick auf "Suchen"
    if st.button("Suche in PubMed (vereinfacht)"):
        query = " OR ".join([w.strip() for w in codewords.split(",") if w.strip()])
        st.session_state["last_query"] = query
        st.write(f"Suche nach: {query}")

        # Evtl. rudimentäre PubMed-Abfrage
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 5}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            st.write("Gefundene PMIDs:", pmids)
            # In st.session_state ablegen?
            st.session_state["fetched_pmids"] = pmids
        else:
            st.error(f"Fehler PubMed: {r.status_code}")
