import streamlit as st
import requests
import openai
import pandas as pd
import os
import time

##############################################################################
# 1) Verbindungstest-Funktionen
##############################################################################

def check_pubmed_connection(timeout=5):
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

def check_europe_pmc_connection(timeout=5):
    test_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": "test", "format": "json", "pageSize": 1}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return ("resultList" in data and "result" in data["resultList"])
    except Exception:
        return False

def check_google_scholar_connection(timeout=5):
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs("test")
        _ = next(search_results)
        return True
    except Exception:
        return False

def check_semantic_scholar_connection(timeout=5):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": "test", "limit": 1, "fields": "title"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "data" in data
    except Exception:
        return False

def check_openalex_connection(timeout=5):
    url = "https://api.openalex.org/works"
    params = {"search": "test", "per_page": 1}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "results" in data
    except Exception:
        return False

def check_core_connection(api_key="", timeout=5):
    if not api_key:
        return False
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"q": "test", "limit": 1}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "results" in data
    except Exception:
        return False

def check_chatgpt_connection():
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return False
    try:
        openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Short connectivity test. Reply with any short message."}],
            max_tokens=10,
            temperature=0
        )
        return True
    except Exception:
        return False

##############################################################################
# 2) API-Suchfunktionen (PubMed, Europe PMC, etc.)
##############################################################################

def esearch_pubmed(query: str, max_results=100, timeout=10):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def get_pubmed_details(pmids: list):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for pmid in pmids:
            info = data.get("result", {}).get(pmid, {})
            results.append({
                "Source": "PubMed",
                "Title": info.get("title", "n/a"),
                "PubMed ID": pmid,
                "DOI": info.get("elocationid", "n/a"),
                "Year": info.get("pubdate", "n/a")[:4] if info.get("pubdate") else "n/a",
                "Abstract": "Abstract nicht abgerufen",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Fehler beim Abrufen von PubMed-Daten: {e}")
        return []

def search_pubmed(query: str, max_results=100):
    pmids = esearch_pubmed(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

def search_europe_pmc(query: str, max_results=100):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": max_results}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("resultList", {}).get("result", []):
            results.append({
                "Source": "Europe PMC",
                "Title": item.get("title", "n/a"),
                "PubMed ID": item.get("pmid", "n/a"),
                "DOI": item.get("doi", "n/a"),
                "Year": str(item.get("pubYear", "n/a")),
                "Abstract": item.get("abstractText", "n/a"),
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"Europe PMC-Suche fehlgeschlagen: {e}")
        return []

def search_google_scholar(query: str, max_results=100):
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs(query)
        results = []
        count = 0
        for pub in search_results:
            if count >= max_results:
                break
            bib = pub.get("bib", {})
            title = bib.get("title", "n/a")
            year = bib.get("pub_year", "n/a")
            results.append({
                "Source": "Google Scholar",
                "Title": title,
                "PubMed ID": "n/a",
                "DOI": "n/a",
                "Year": year,
                "Abstract": "Abstract nicht verfügbar",
                "Population": "n/a"
            })
            count += 1
        return results
    except Exception as e:
        st.error(f"Fehler bei der Google Scholar Suche: {e}")
        return []

def search_semantic_scholar(query: str, max_results=100, retries=3, delay=5):
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": max_results, "fields": "title,authors,year,abstract"}
    attempt = 0
    while attempt < retries:
        try:
            r = requests.get(base_url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            papers = data.get("data", [])
            results = []
            for paper in papers:
                results.append({
                    "Source": "Semantic Scholar",
                    "Title": paper.get("title", "n/a"),
                    "PubMed ID": "n/a",
                    "DOI": "n/a",
                    "Year": str(paper.get("year", "n/a")),
                    "Abstract": paper.get("abstract", "n/a"),
                    "Population": "n/a"
                })
            return results
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                st.warning(f"Rate limit bei Semantic Scholar erreicht, warte {delay} Sekunden und versuche es erneut...")
                time.sleep(delay)
                attempt += 1
                continue
            else:
                st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
                return []
        except Exception as e:
            st.error(f"Fehler bei der Semantic Scholar-Suche: {e}")
            return []
    st.error("Semantic Scholar API: Rate limit überschritten. Bitte später erneut versuchen.")
    return []

def search_openalex(query: str, max_results=100):
    url = "https://api.openalex.org/works"
    params = {"search": query, "per_page": max_results}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = []
        for work in data.get("results", []):
            title = work.get("display_name", "n/a")
            doi = work.get("doi", "n/a")
            pub_year = work.get("publication_year", "n/a")
            authorship_list = work.get("authorships", [])
            authors = ", ".join([a.get("author", {}).get("display_name", "n/a") for a in authorship_list])
            results.append({
                "Source": "OpenAlex",
                "Title": title,
                "PubMed ID": "n/a",
                "DOI": doi,
                "Year": str(pub_year),
                "Abstract": "Abstract nicht verfügbar",
                "Population": "n/a"
            })
        return results
    except Exception as e:
        st.error(f"OpenAlex-Suche fehlgeschlagen: {e}")
        return []

class CoreAPI:
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=10):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = []
            for key, value in filters.items():
                filter_expressions.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort
        r = requests.get(self.base_url + endpoint, headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

def search_core(query: str, max_results=100):
    core_api_key = st.secrets.get("CORE_API_KEY", "")
    if not core_api_key:
        st.error("CORE API Key fehlt!")
        return []
    core_api = CoreAPI(core_api_key)
    try:
        result = core_api.search_publications(query, limit=max_results)
        pubs = result.get("results", [])
        transformed = []
        for pub in pubs:
            transformed.append({
                "Source": "CORE",
                "Title": pub.get("title", "Kein Titel verfügbar"),
                "PubMed ID": "n/a",
                "DOI": pub.get("doi", "n/a"),
                "Year": pub.get("publicationDate", "n/a"),
                "Abstract": "Abstract nicht verfügbar",
                "Population": "n/a"
            })
        return transformed
    except Exception as e:
        st.error(f"CORE API Anfrage fehlgeschlagen: {e}")
        return []

##############################################################################
# 3) Gene-Liste: Laden aus Excel
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Liest ab Spalte C, Zeile 3 (Index [2, 2]) die Gene aus 'genes.xlsx' in 'modules'
    und gibt sie als Liste zurück.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        gene_series = df.iloc[2:, 2]  # ab Zeile 3, Spalte C
        return gene_series.dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 4) Einstellungen & Profile
##############################################################################

def save_current_settings(profile_name: str, use_pubmed: bool, use_epmc: bool, use_google: bool,
                          use_semantic: bool, use_openalex: bool, use_core: bool, use_chatgpt: bool,
                          sheet_choice: str, codewords: str):
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {}
    st.session_state["profiles"][profile_name] = {
        "use_pubmed": use_pubmed,
        "use_epmc": use_epmc,
        "use_google": use_google,
        "use_semantic": use_semantic,
        "use_openalex": use_openalex,
        "use_core": use_core,
        "use_chatgpt": use_chatgpt,
        "sheet_choice": sheet_choice,
        "codewords": codewords
    }
    st.success(f"Profil '{profile_name}' erfolgreich gespeichert. (Nächstes Modul kann es nun laden.)")

def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        return profiles.get(profile_name, None)
    return None

##############################################################################
# 5) Haupt-Modul
##############################################################################

def module_online_api_filter():
    st.title("Codewords + Gene (buchstabenweise auswählen) → API-Suche, inkl. Profil-Speichern")

    # Profilverwaltung
    st.subheader("Profilverwaltung")
    profile_name_input = st.text_input("Profilname eingeben (für Speichern/Laden):", "")
    existing_profiles = list(st.session_state.get("profiles", {}).keys())
    selected_profile_to_load = st.selectbox("Profil zum Laden auswählen:", ["(kein)"] + existing_profiles)
    if st.button("Profil laden"):
        if selected_profile_to_load != "(kein)":
            loaded = load_settings(selected_profile_to_load)
            if loaded:
                st.session_state["current_settings"] = loaded
                st.success(f"Profil '{selected_profile_to_load}' geladen.")
            else:
                st.warning(f"Profil '{selected_profile_to_load}' nicht gefunden.")
        else:
            st.info("Kein Profil zum Laden ausgewählt.")

    # Default-Einstellungen (falls nichts in Session)
    if "current_settings" not in st.session_state:
        st.session_state["current_settings"] = {
            "use_pubmed": True,
            "use_epmc": True,
            "use_google": False,
            "use_semantic": False,
            "use_openalex": False,
            "use_core": False,
            "use_chatgpt": False,
            "sheet_choice": "",
            "codewords": ""
        }
    current = st.session_state["current_settings"]

    # API-Auswahl
    st.subheader("API-Auswahl")
    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=current["use_pubmed"])
        use_epmc = st.checkbox("Europe PMC", value=current["use_epmc"])
        use_google = st.checkbox("Google Scholar", value=current["use_google"])
        use_semantic = st.checkbox("Semantic Scholar", value=current["use_semantic"])
    with col2:
        use_openalex = st.checkbox("OpenAlex", value=current["use_openalex"])
        use_core = st.checkbox("CORE", value=current["use_core"])
        use_chatgpt = st.checkbox("ChatGPT (optional)", value=current["use_chatgpt"])

    # Verbindungstest
    if st.button("Verbindung prüfen"):
        def green_dot(): return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot(): return "<span style='color: red; font-size: 20px;'>&#9679;</span>"
        checks = []
        if use_pubmed:
            checks.append(f"{green_dot() if check_pubmed_connection() else red_dot()} <strong>PubMed</strong>")
        if use_epmc:
            checks.append(f"{green_dot() if check_europe_pmc_connection() else red_dot()} <strong>Europe PMC</strong>")
        if use_google:
            checks.append(f"{green_dot() if check_google_scholar_connection() else red_dot()} <strong>Google Scholar</strong>")
        if use_semantic:
            checks.append(f"{green_dot() if check_semantic_scholar_connection() else red_dot()} <strong>Semantic Scholar</strong>")
        if use_openalex:
            checks.append(f"{green_dot() if check_openalex_connection() else red_dot()} <strong>OpenAlex</strong>")
        if use_core:
            ckey = st.secrets.get("CORE_API_KEY", "")
            checks.append(f"{green_dot() if check_core_connection(ckey) else red_dot()} <strong>CORE</strong>")
        if use_chatgpt:
            checks.append(f"{green_dot() if check_chatgpt_connection() else red_dot()} <strong>ChatGPT</strong>")
        st.markdown(" &nbsp;&nbsp;&nbsp; ".join(checks), unsafe_allow_html=True)

    # Codewords
    st.subheader("Codewords (OR-Suche)")
    codewords_text = st.text_area("Codewörter:", value=current["codewords"], height=60)

    # Genes aus Excel
    st.write("---")
    st.subheader("Genes aus Excel (Spalte C ab Zeile 3) buchstabenweise filtern")
    use_genes = st.checkbox("Genes zusätzlich einbeziehen?", value=True)
    chosen_genes = []
    sheet_choice = ""
    if use_genes:
        excel_path = os.path.join("modules", "genes.xlsx")
        if not os.path.exists(excel_path):
            st.error("genes.xlsx nicht gefunden in 'modules/'.")
            return
        try:
            xls = pd.ExcelFile(excel_path)
            sheet_names = xls.sheet_names
        except Exception as e:
            st.error(f"Fehler beim Öffnen von genes.xlsx: {e}")
            return
        if not sheet_names:
            st.error("Keine Sheets in genes.xlsx gefunden.")
            return

        current_sheet = current.get("sheet_choice", sheet_names[0])
        if current_sheet not in sheet_names:
            current_sheet = sheet_names[0]
        sheet_choice = st.selectbox("Welches Sheet?", sheet_names, index=sheet_names.index(current_sheet))

        all_genes = load_genes_from_excel(sheet_choice)
        if all_genes:
            # Buchstaben
            letters = sorted(set(g[0].upper() for g in all_genes if g))
            letter_choice = st.selectbox("Wähle Anfangsbuchstaben:", options=["(Kein)"] + letters)
            filtered_genes = []
            if letter_choice != "(Kein)":
                filtered_genes = [g for g in all_genes if g and g[0].upper() == letter_choice]

            chosen_genes = st.multiselect("Ausgewählte Gene:", filtered_genes)
        else:
            st.info("Keine Gene geladen oder Excel-Sheet leer.")

    # Such-Button
    st.write("---")
    st.subheader("Suche starten")
    if st.button("Suche in APIs"):
        raw_codewords = [w.strip() for w in codewords_text.replace(",", " ").split() if w.strip()]

        if use_genes and chosen_genes:
            raw_codewords.extend(chosen_genes)

        if not raw_codewords:
            st.warning("Keine Codewörter bzw. Gene angegeben.")
            return

        final_query = " OR ".join(raw_codewords)
        st.write(f"**Finale Suchanfrage:** {final_query}")

        total_res = []
        if use_pubmed:
            p_res = search_pubmed(final_query)
            st.write(f"PubMed: {len(p_res)} Treffer")
            total_res.extend(p_res)
        if use_epmc:
            e_res = search_europe_pmc(final_query)
            st.write(f"Europe PMC: {len(e_res)} Treffer")
            total_res.extend(e_res)
        if use_google:
            g_res = search_google_scholar(final_query)
            st.write(f"Google Scholar: {len(g_res)} Treffer")
            total_res.extend(g_res)
        if use_semantic:
            s_res = search_semantic_scholar(final_query)
            st.write(f"Semantic Scholar: {len(s_res)} Treffer")
            total_res.extend(s_res)
        if use_openalex:
            o_res = search_openalex(final_query)
            st.write(f"OpenAlex: {len(o_res)} Treffer")
            total_res.extend(o_res)
        if use_core:
            c_res = search_core(final_query)
            st.write(f"CORE: {len(c_res)} Treffer")
            total_res.extend(c_res)

        if not total_res:
            st.info("Keine Treffer gefunden in den ausgewählten APIs.")
        else:
            df = pd.DataFrame(total_res)
            st.dataframe(df)

    # Profil speichern
    st.write("---")
    st.subheader("Profil speichern (für nächstes Modul)")

    if st.button("Profil speichern"):
        pname = profile_name_input.strip()
        if not pname:
            st.warning("Bitte einen Profilnamen eingeben.")
        else:
            save_current_settings(
                pname,
                use_pubmed,
                use_epmc,
                use_google,
                use_semantic,
                use_openalex,
                use_core,
                use_chatgpt,
                sheet_choice if use_genes else "",
                codewords_text
            )

    # Session State updaten (damit das neu geladene Profil erhalten bleibt)
    st.session_state["current_settings"] = {
        "use_pubmed": use_pubmed,
        "use_epmc": use_epmc,
        "use_google": use_google,
        "use_semantic": use_semantic,
        "use_openalex": use_openalex,
        "use_core": use_core,
        "use_chatgpt": use_chatgpt,
        "sheet_choice": sheet_choice if use_genes else "",
        "codewords": codewords_text
    }

def main():
    st.title("Multi-API mit Genes + Codewords, Profil-Speicherung")
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {}
    module_online_api_filter()

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    main()
