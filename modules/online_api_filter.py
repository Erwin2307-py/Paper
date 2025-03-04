# file: codewords_pubmed.py

import streamlit as st
import requests

def esearch_pubmed(query: str, max_results=5, timeout=10):
    """
    Beispiel-Funktion: Ruft eine einfache PubMed-Suche (esearch) auf und 
    gibt eine Liste von PMID zurück (max. 5).
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

def module_codewords_pubmed():
    """
    Dieses Modul:
      - Zeigt ein Dropdown aller gespeicherten Profile in st.session_state["profiles"].
      - Beim Auswählen eines Profils werden dessen Einstellungen angezeigt.
      - Anschließend kann man eine Suchanfrage starten, 
        die (zumindest demonstrativ) PubMed mit 'test' oder Codewörtern abfragt,
        abhängig von den Profil-Einstellungen (z. B. use_pubmed).
      - Man kann beliebig viele Codewörter eingeben (kommasepariert) 
        und per AND/OR verknüpfen. 
    """
    st.title("Profile-basiertes Modul: Codewörter & PubMed-Suche")

    # 1) Prüfen, ob Profile vorliegen
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte zuerst im anderen Modul ein Profil anlegen/speichern.")
        return

    # Liste der Profil-Namen
    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(Kein Profil)"] + profile_names)

    if chosen_profile == "(Kein Profil)":
        st.info("Bitte wähle ein Profil aus, um die Einstellungen anzuzeigen.")
        return

    # Profil-Einstellungen laden
    profile_data = st.session_state["profiles"][chosen_profile]

    st.write("**Gewählte Einstellungen im Profil**:")
    st.json(profile_data)  # Zeigt z. B. ein JSON-Feld mit den API-Settings

    # 2) Mehrere Codewörter eingeben
    codewords_str = st.text_input("Codewörter (kommasepariert):", "")
    st.write("Z. B. `genotyp, snp, phänotyp`")

    # 3) Logik wählen (AND/OR)
    logic_option = st.radio("Verknüpfung der Codewörter:", ["AND", "OR"], index=1)

    # 4) Button: Suche starten
    if st.button("Suche nach Papers"):
        # Parse Codewörter
        words = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not words:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        # Aus Profil-Einstellungen z. B. use_pubmed auslesen
        use_pubmed = profile_data.get("use_pubmed", False)
        # (Du könntest auch Europe PMC, CORE etc. hier verarbeiten, 
        #  je nachdem was du suchst, wir machen in diesem Beispiel nur PubMed.)

        if not use_pubmed:
            st.info("Dieses Profil hat 'PubMed' nicht aktiviert. Es erfolgt keine PubMed-Suche.")
            return

        # Build query
        if logic_option == "AND":
            # "word1 AND word2 AND ..."
            query_str = " AND ".join(words)
        else:
            # "word1 OR word2 OR ..."
            query_str = " OR ".join(words)

        st.write(f"PubMed-Suchanfrage: `{query_str}`")
        pmids = esearch_pubmed(query_str)
        if not pmids:
            st.info("Keine PMID gefunden.")
        else:
            st.write("Gefundene PMIDs:")
            st.write(pmids)

    st.write("---")
    st.info("Dieses Modul liest ein Profil aus und nutzt Codewörter + AND/OR für eine PubMed-Suche.")
