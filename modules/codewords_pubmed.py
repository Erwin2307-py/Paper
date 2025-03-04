# file: codewords_pubmed.py

import streamlit as st
import requests

def esearch_pubmed(query: str, max_results=10, timeout=10):
    """
    Ruft eine einfache PubMed-Suche (esearch) auf und gibt Liste von PMID zurück.
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
      - Liest ggf. vorhandene Profile/Einstellungen aus st.session_state,
      - Zeigt Eingabefelder für Codewörter,
      - Lässt den Nutzer AND/OR-Logik wählen,
      - Baut eine Suchanfrage,
      - Demonstriert eine PubMed-Suche (esearch) und zeigt erste PMID-Ergebnisse.
    """
    st.title("Codewords & PubMed (Mehrere Codewörter, AND/OR)")

    # 1) Check, ob ein Profil/Einstellungen geladen sind:
    current_profile = None
    if "current_settings" in st.session_state:
        current_profile = st.session_state["current_settings"]
    
    st.write("**Aktuelles Profil**:", current_profile if current_profile else "(Kein Profil geladen / keine settings)")

    st.subheader("Codewörter & Suchlogik")

    # 2) Eingabefeld für mehrere Codewörter (z. B. kommasepariert)
    codewords_str = st.text_input("Codewörter (kommagetrennt oder Leerzeichen):", "")
    st.write("Beispiel: `genotyp, SNP, phänotyp`")

    # 3) AND/OR-Logik
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)
    st.write("Du kannst die Codewörter via 'AND' oder 'OR' verbinden.")

    # 4) Button: Starte PubMed-Suche
    if st.button("PubMed-Suche starten"):
        # Codewörter parsen
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        # Bauen einer (sehr einfachen) PubMed-Suchanfrage:
        # Logik: z. B. (term1 [Title/Abstract]) AND (term2 [Title/Abstract]) ...
        # hier Demo, wir machen nur (term1 OR term2), etc., ohne Felder
        # Du könntest "[Title/Abstract]" anhängen, hier nur Demo:
        if logic_option == "AND":
            # "(term1 AND term2 AND term3)"
            joined = " AND ".join(raw_list)
        else:
            # OR
            joined = " OR ".join(raw_list)

        st.write("Finale PubMed-Suchanfrage (Demo):", joined)
        pmids = esearch_pubmed(joined, max_results=10)
        if not pmids:
            st.info("Keine PMID gefunden.")
        else:
            st.write("Gefundene PMIDs:", pmids)

    st.write("---")
    st.info("Fertig. Dieses Modul kann Profil-Infos anzeigen und Codewörter mit AND/OR-Logik für PubMed verbinden.")
