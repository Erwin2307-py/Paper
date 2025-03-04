# file: codewords_pubmed.py

import streamlit as st
import requests

def esearch_pubmed(query: str, max_results=100, timeout=10):
    """
    Führt eine PubMed-Suche über E-Utilities aus und gibt eine Liste von PMID zurück.
    Es werden maximal max_results (standard 100) Treffer zurückgegeben.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        return pmids
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def esearch_europe_pmc(query: str, pageSize=100, timeout=10):
    """
    Führt eine Europe PMC-Suche aus und gibt eine Liste von IDs zurück.
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": pageSize
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        results = data.get("resultList", {}).get("result", [])
        ids = []
        for item in results:
            pmid = item.get("pmid", "")
            if pmid:
                ids.append("PMID:" + pmid)
        return ids
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return []

def module_codewords_pubmed():
    """
    Dieses Modul:
      - Zeigt ein Dropdown-Menü aller in st.session_state gespeicherten Profile.
      - Übernimmt beim Laden eines Profils die API‑Einstellungen.
      - Ermöglicht die Eingabe mehrerer Codewörter sowie die Wahl der Verknüpfungslogik (AND/OR).
      - Baut daraus eine Suchanfrage und führt für jede aktivierte API (PubMed und Europe PMC) eine Suche mit mindestens 100 Treffern durch.
      - Zeigt die gefundenen IDs an.
    """
    st.title("Codewörter & Multi-API-Suche (min. 100 Treffer pro API)")

    # 1) Profil auswählen
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte erst in einem anderen Modul ein Profil speichern.")
        return

    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = st.session_state["profiles"][chosen_profile]
    st.subheader("Geladene Profileinstellungen")
    st.json(profile_data)  # Zeigt die Einstellungen als JSON an

    # 2) Codewörter eingeben
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommaseparat oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Verknüpfung:", options=["AND", "OR"], index=1)

    # 3) Suchanfrage zusammenbauen
    if st.button("Suche starten"):
        # Parst die Codewörter
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        if logic_option == "AND":
            query_str = " AND ".join(raw_list)
        else:
            query_str = " OR ".join(raw_list)

        st.write("Zusammengesetzte Suchanfrage:", query_str)

        # 4) Suche in den aktivierten APIs aus dem Profil
        # Beispiel: PubMed
        if profile_data.get("use_pubmed", False):
            st.write("### PubMed")
            pmids = esearch_pubmed(query_str, max_results=100)
            if pmids:
                st.write(f"Gefundene PMIDs (max. 100): {len(pmids)}")
                st.write(pmids)
            else:
                st.info("Keine Ergebnisse in PubMed gefunden.")

        # Beispiel: Europe PMC
        if profile_data.get("use_epmc", False):
            st.write("### Europe PMC")
            ids_epmc = esearch_europe_pmc(query_str, pageSize=100)
            if ids_epmc:
                st.write(f"Gefundene Europe PMC IDs (max. 100): {len(ids_epmc)}")
                st.write(ids_epmc)
            else:
                st.info("Keine Ergebnisse in Europe PMC gefunden.")

    st.write("---")
    st.info("Dieses Modul verwendet das ausgewählte Profil und verbindet eingegebene Codewörter mittels AND/OR für die Suche in PubMed und Europe PMC.")

