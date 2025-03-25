import streamlit as st
import requests
import openai
import pandas as pd
import re
import xml.etree.ElementTree as ET
import os

try:
    from scholarly import scholarly
except ImportError:
    pass  # Falls Scholarly nicht installiert ist

###############################################################################
# Hilfsfunktionen
###############################################################################

def load_profile(profile_name: str):
    """Zentrales Laden des Profils aus st.session_state (gespeichert in Skript 1)."""
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
    return None

# --- PubMed-Funktionen ---
def esearch_pubmed(query: str, max_results=100, timeout=10):
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
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def parse_efetch_response(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    pmid_abstract_map = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid_val = pmid_el.text if pmid_el is not None else None
        abstract_el = article.find(".//AbstractText")
        abstract_text = abstract_el.text if abstract_el is not None else "n/a"
        if pmid_val:
            pmid_abstract_map[pmid_val] = abstract_text
    return pmid_abstract_map

def fetch_pubmed_abstracts(pmids, timeout=10):
    if not pmids:
        return {}
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return parse_efetch_response(r.text)
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Abstracts: {e}")
        return {}

def get_pubmed_details(pmids: list):
    if not pmids:
        return []
    url_summary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params_sum = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    try:
        r_sum = requests.get(url_summary, params=params_sum, timeout=10)
        r_sum.raise_for_status()
        data_summary = r_sum.json()
    except Exception as e:
        st.error(f"Fehler bei PubMed-ESummary: {e}")
        return []

    abstracts_map = fetch_pubmed_abstracts(pmids)

    results = []
    for pmid in pmids:
        info = data_summary.get("result", {}).get(pmid, {})
        if not info or pmid == "uids":
            continue
        pubdate = info.get("pubdate", "n/a")
        pubyear = pubdate[:4] if len(pubdate) >= 4 else "n/a"
        doi = info.get("elocationid", "n/a")
        title = info.get("title", "n/a")
        abs_text = abstracts_map.get(pmid, "n/a")
        publisher = info.get("fulljournalname") or info.get("source") or "n/a"

        results.append({
            "Source": "PubMed",
            "Title": title,
            "PubMed ID": pmid,
            "Abstract": abs_text,
            "DOI": doi,
            "Year": pubyear,
            "Publisher": publisher,
            "Population": "n/a"
        })
    return results

def search_pubmed(query: str, max_results=100):
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

# --- Europe PMC ---
def search_europe_pmc(query: str, max_results=100, timeout=10):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": max_results}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("resultList", {}).get("result", []):
            pub_year = str(item.get("pubYear", "n/a"))
            abstract_text = item.get("abstractText", "n/a")
            jinfo = item.get("journalInfo", {})
            publisher = jinfo.get("journal", "n/a") if isinstance(jinfo, dict) else "n/a"
            results.append({
                "Source": "Europe PMC",
                "Title": item.get("title", "n/a"),
                "PubMed ID": item.get("pmid", "n/a"),
                "Abstract": abstract_text,
                "DOI": item.get("doi", "n/a"),
                "Year": pub_year,
                "Publisher": publisher,
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return []

# --- Google Scholar ---
def search_google_scholar(query: str, max_results=100):
    results = []
    try:
        from scholarly import scholarly
        for idx, pub in enumerate(scholarly.search_pubs(query)):
            if idx >= max_results:
                break
            bib = pub.get("bib", {})
            title = bib.get("title", "n/a")
            year = bib.get("pub_year", "n/a")
            abstract_ = bib.get("abstract", "n/a")
            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": "n/a",
                "Year": str(year),
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Google Scholar-Suche fehlgeschlagen: {e}")
        return []

# --- Semantic Scholar ---
def search_semantic_scholar(query: str, max_results=100):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": max_results, "fields": "title,authors,year,abstract"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for p in data.get("data", []):
            year_ = str(p.get("year", "n/a"))
            abstract_ = p.get("abstract", "n/a")
            results.append({
                "Source": "Semantic Scholar",
                "Title": p.get("title", "n/a"),
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": "n/a",
                "Year": year_,
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Semantic Scholar-Suche fehlgeschlagen: {e}")
        return []

# --- OpenAlex ---
def search_openalex(query: str, max_results=100):
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": max_results}
    results = []
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        for w in data.get("results", []):
            title = w.get("display_name", "n/a")
            year_ = str(w.get("publication_year", "n/a"))
            doi = w.get("doi", "n/a")
            abstract_ = "n/a"
            results.append({
                "Source": "OpenAlex",
                "Title": title,
                "PubMed ID": "n/a",
                "Abstract": abstract_,
                "DOI": doi,
                "Year": year_,
                "Publisher": "n/a",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"OpenAlex-Suche fehlgeschlagen: {e}")
        return results

# --- CORE (falls gewünscht) ---
def search_core(query: str, max_results=10):
    core_api_key = st.secrets.get("CORE_API_KEY", "")
    if not core_api_key:
        st.error("CORE API Key fehlt! Bitte in st.secrets['CORE_API_KEY'] hinterlegen.")
        return []
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {core_api_key}"}
    params = {"q": query, "limit": max_results}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        pubs = data.get("results", [])
        results = []
        for pub in pubs:
            results.append({
                "Source": "CORE",
                "Title": pub.get("title", "n/a"),
                "PubMed ID": "n/a",
                "Abstract": "n/a",
                "DOI": pub.get("doi", "n/a"),
                "Year": pub.get("publicationDate", "n/a"),
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"CORE API Anfrage fehlgeschlagen: {e}")
        return []

###############################################################################
# ChatGPT-Scoring mit Genes und Codewords
###############################################################################

def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    """
    Lässt ChatGPT jedes Paper scoren (0-100) basierend auf Codewörtern + Genen.
    Zeigt dabei an, welches Paper gerade verarbeitet wird.
    """
    if not papers:
        return []

    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("Kein 'OPENAI_API_KEY' in st.secrets hinterlegt.")
        return []

    scored_results = []
    total = len(papers)
    progress = st.progress(0)
    status_text = st.empty()  # Platzhalter für Status-Informationen

    genes_str = ", ".join(genes) if genes else ""

    for idx, paper in enumerate(papers, start=1):
        # Update Status: Zeige an, welches Paper aktuell verarbeitet wird.
        current_title = paper.get("Title", "n/a")
        status_text.text(f"Verarbeite Paper {idx}/{total}: {current_title}")
        progress.progress(idx / total)
        title = paper.get("Title", "n/a")
        abstract = paper.get("Abstract", "n/a")

        prompt = (
            f"Codewörter: {codewords}\n"
            f"Gene: {genes_str}\n\n"
            f"Paper:\n"
            f"Titel: {title}\n"
            f"Abstract:\n{abstract}\n\n"
            "Gib mir eine Zahl von 0 bis 100 (Relevanz), "
            "wobei sowohl Codewörter als auch Gene berücksichtigt werden."
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0
            )
            raw_text = resp.choices[0].message.content.strip()
            match = re.search(r'(\d+)', raw_text)
            if match:
                score = int(match.group(1))
            else:
                score = 0
        except Exception as e:
            st.error(f"ChatGPT Fehler beim Scoring: {e}")
            score = 0

        new_item = dict(paper)
        new_item["Relevance"] = score
        scored_results.append(new_item)

    # Status-Platzhalter leeren, wenn fertig.
    status_text.empty()
    progress.empty()
    scored_results.sort(key=lambda x: x["Relevance"], reverse=True)
    return scored_results[:top_k]

###############################################################################
# Haupt-Funktion: Multi-API-Suche + ChatGPT
###############################################################################

def module_codewords_pubmed():
    st.title("Modul 2: Multi-API-Suche + ChatGPT-Scoring (Profil-Übernahme)")

    # 1) Profil auswählen
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Noch keine Profile vorhanden! (Skript 1 ausführen)")
        return

    profiles_list = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Profil wählen:", ["(kein)"] + profiles_list)
    if chosen_profile == "(kein)":
        st.info("Kein Profil gewählt.")
        return

    profile_data = load_profile(chosen_profile)
    if not profile_data:
        st.warning("Profil nicht gefunden oder leer.")
        return

    st.write("**Geladenes Profil**:")
    st.json(profile_data)

    # Daten extrahieren
    use_pubmed = profile_data.get("use_pubmed", False)
    use_epmc = profile_data.get("use_epmc", False)
    use_google = profile_data.get("use_google", False)
    use_semantic = profile_data.get("use_semantic", False)
    use_openalex = profile_data.get("use_openalex", False)
    use_core = profile_data.get("use_core", False)
    use_chatgpt = profile_data.get("use_chatgpt", False)

    selected_genes = profile_data.get("selected_genes", [])
    if not selected_genes and profile_data.get("final_gene"):
        selected_genes = [profile_data["final_gene"]]

    codewords_str = profile_data.get("codewords_str", "")

    # NEU: Zusätzliches manuelles Codewort
    manual_codeword = st.text_input("Manuelles Codewort (optional) eingeben:")
    if manual_codeword.strip():
        # Falls der Nutzer ein manuelles Codewort eingegeben hat, fügen wir es hinzu
        if codewords_str.strip():
            codewords_str += " " + manual_codeword.strip()
        else:
            codewords_str = manual_codeword.strip()

    # 2) Such-Logik
    st.subheader("Such-Logik (AND / OR für Codewörter/Gene)")
    logic_option = st.radio("Logik:", ["AND", "OR"], index=1)

    if st.button("Suche starten"):
        # Query bauen
        raw_cws = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if logic_option == "AND":
            query_str = " AND ".join(raw_cws) if raw_cws else ""
        else:
            query_str = " OR ".join(raw_cws) if raw_cws else ""

        if selected_genes:
            genes_query = " OR ".join(selected_genes)
            if query_str:
                query_str = f"({query_str}) OR ({genes_query})"
            else:
                query_str = genes_query

        if not query_str.strip():
            st.warning("Leere Suchanfrage (keine Codewörter + keine Gene). Abbruch.")
            return

        st.write(f"**Finale Query:** {query_str}")

        all_results = []

        # Auf APIs loslassen
        if use_pubmed:
            pm = search_pubmed(query_str, max_results=150)
            st.write(f"PubMed: {len(pm)} Treffer")
            all_results.extend(pm)

        if use_epmc:
            ep = search_europe_pmc(query_str, max_results=150)
            st.write(f"Europe PMC: {len(ep)} Treffer")
            all_results.extend(ep)

        if use_google:
            gg = search_google_scholar(query_str, max_results=50)  # Google Scholar is slow / rate-limited
            st.write(f"Google Scholar: {len(gg)} Treffer")
            all_results.extend(gg)

        if use_semantic:
            se = search_semantic_scholar(query_str, max_results=100)
            st.write(f"Semantic Scholar: {len(se)} Treffer")
            all_results.extend(se)

        if use_openalex:
            oa = search_openalex(query_str, max_results=100)
            st.write(f"OpenAlex: {len(oa)} Treffer")
            all_results.extend(oa)

        if use_core:
            co = search_core(query_str, max_results=50)
            st.write(f"CORE: {len(co)} Treffer")
            all_results.extend(co)

        if not all_results:
            st.info("Keine Treffer gefunden.")
            return

        st.session_state["search_results"] = all_results
        st.write(f"**Gesamtanzahl** gefundener Papers: {len(all_results)}")

    # Ergebnisse anzeigen + ChatGPT-Scoring
    if "search_results" in st.session_state and st.session_state["search_results"]:
        df_main = pd.DataFrame(st.session_state["search_results"])
        st.dataframe(df_main)

        if use_chatgpt:
            st.subheader("ChatGPT Relevanz-Scoring")
            if st.button("Scoring ausführen"):
                # Begrenzung, z.B. max 200, um Kosten zu minimieren
                all_found = st.session_state["search_results"]
                if len(all_found) > 200:
                    all_found = all_found[:200]

                scored_list = chatgpt_online_search_with_genes(
                    papers=all_found,
                    codewords=codewords_str,
                    genes=selected_genes,
                    top_k=200
                )
                st.subheader("Top-Ergebnisse nach Relevanz")
                df_scored = pd.DataFrame(scored_list)
                st.dataframe(df_scored)
        else:
            st.info("ChatGPT ist im gewählten Profil nicht aktiviert (use_chatgpt=False).")

def main():
    st.set_page_config(layout="wide")
    module_codewords_pubmed()

if __name__ == "__main__":
    main()
