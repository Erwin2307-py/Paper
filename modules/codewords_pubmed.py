import streamlit as st
import requests
import openai
import pandas as pd
import os
import time

##############################
# 1) Verbindungstest-Funktionen für diverse APIs
##############################

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

##############################
# 2) API-Suchfunktionen
##############################

# PubMed
def esearch_pubmed_api(query: str, max_results=100, timeout=10):
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
    pmids = esearch_pubmed_api(query, max_results=max_results)
    if not pmids:
        return []
    return get_pubmed_details(pmids)

# Europe PMC
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

# Google Scholar (echt, via scholarly)
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

# Semantic Scholar
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

# OpenAlex (echt)
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

# CORE Aggregate (echt)
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
# 3) Gene-Loader: Liest ab C3 eines gegebenen Sheets
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        gene_series = df.iloc[2:, 2]  # Ab Zeile 3, Spalte C
        return gene_series.dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 4) ChatGPT-Funktion zum Filtern
##############################################################################

def check_genes_in_text_with_chatgpt(text: str, genes: list, model="gpt-3.5-turbo") -> dict:
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY'] hinterlegt!")
        return {}
    if not text.strip():
        st.warning("Kein Text eingegeben.")
        return {}
    if not genes:
        st.info("Keine Gene in der Liste (Sheet leer?).")
        return {}
    joined_genes = ", ".join(genes)
    prompt = (
        f"Hier ist ein Text:\n\n{text}\n\n"
        f"Hier eine Liste von Genen: {joined_genes}\n"
        f"Gib für jedes Gen an, ob es im Text vorkommt (Yes) oder nicht (No).\n"
        f"Antworte in der Form:\n"
        f"GENE: Yes\nGENE2: No\n"
    )
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
        result_map = {}
        for line in answer.split("\n"):
            if ":" in line:
                parts = line.split(":", 1)
                gene_name = parts[0].strip()
                yes_no = parts[1].strip().lower()
                result_map[gene_name] = ("yes" in yes_no)
        return result_map
    except Exception as e:
        st.error(f"ChatGPT Fehler: {e}")
        return {}

##############################################################################
# 5) Einstellungen speichern/laden (Profile)
##############################################################################

def save_current_settings(profile_name: str, use_pubmed: bool, use_epmc: bool, use_google: bool,
                          use_semantic: bool, use_openalex: bool, use_core: bool, use_chatgpt: bool,
                          sheet_choice: str, text_input: str):
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
        "text_input": text_input
    }
    st.success(f"Profil '{profile_name}' erfolgreich gespeichert.")

def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        return profiles.get(profile_name, None)
    return None

##############################################################################
# 6) Haupt-Modul: Codewörter & Multi-API-Suche
##############################################################################

def module_codewords_pubmed():
    st.title("Codewörter & Multi-API-Suche (mind. 100 Paper pro API)")

    # 1) Dropdown: Profile auswählen
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile vorhanden. Bitte zuerst ein Profil speichern.")
        return

    profile_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Wähle ein Profil:", ["(kein)"] + profile_names)
    if chosen_profile == "(kein)":
        st.info("Bitte wähle ein Profil aus.")
        return

    profile_data = load_settings(chosen_profile)
    st.subheader("Profil-Einstellungen")
    st.json(profile_data)

    # 2) Eingabefeld für Codewörter und Logik
    st.subheader("Codewörter & Logik")
    codewords_str = st.text_input("Codewörter (kommasepariert oder Leerzeichen):", "")
    st.write("Beispiel: genotyp, SNP, phänotyp")
    logic_option = st.radio("Logik:", options=["AND", "OR"], index=1)

    # 3) Suchanfrage zusammenbauen und API-Suche starten
    if st.button("Suche starten"):
        raw_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        if not raw_list:
            st.warning("Bitte mindestens ein Codewort eingeben.")
            return

        query_str = " AND ".join(raw_list) if logic_option == "AND" else " OR ".join(raw_list)
        st.write("Finale Suchanfrage:", query_str)

        results_all = []

        # Aktivierte APIs laut Profil
        if profile_data.get("use_pubmed", False):
            st.write("### PubMed")
            res = search_pubmed(query_str, max_results=100)
            st.write(f"Anzahl PubMed-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_epmc", False):
            st.write("### Europe PMC")
            res = search_europe_pmc(query_str, max_results=100)
            st.write(f"Anzahl Europe PMC-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_google", False):
            st.write("### Google Scholar")
            res = search_google_scholar(query_str, max_results=100)
            st.write(f"Anzahl Google Scholar-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_semantic", False):
            st.write("### Semantic Scholar")
            res = search_semantic_scholar(query_str, max_results=100)
            st.write(f"Anzahl Semantic Scholar-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_openalex", False):
            st.write("### OpenAlex")
            res = search_openalex(query_str, max_results=100)
            st.write(f"Anzahl OpenAlex-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if profile_data.get("use_core", False):
            st.write("### CORE")
            res = search_core(query_str, max_results=100)
            st.write(f"Anzahl CORE-Ergebnisse: {len(res)}")
            results_all.extend(res)

        if not results_all:
            st.info("Keine Ergebnisse gefunden.")
        else:
            st.write("## Gesamtergebnis aus allen aktivierten APIs")
            df = pd.DataFrame(results_all)
            st.dataframe(df)

    st.write("---")
    st.info("Dieses Modul nutzt das ausgewählte Profil, um Codewörter (mit AND/OR-Verknüpfung) auf alle aktivierten APIs anzuwenden und gibt alle Paper-Informationen aus (Quelle, Titel, PubMed ID, DOI, Jahr, Abstract, Population).")

    # Profil-Einstellungen speichern
    st.session_state["current_settings"] = {
        "use_pubmed": use_pubmed,
        "use_epmc": use_epmc,
        "use_google": use_google,
        "use_semantic": use_semantic,
        "use_openalex": use_openalex,
        "use_core": use_core,
        "use_chatgpt": use_chatgpt,
        "sheet_choice": sheet_choice if st.checkbox("Gene aus Excel verwenden", value=True) else "",
        "text_input": st.text_area("Füge hier deinen Abstract / Text ein:", height=200, value=profile_data.get("text_input", ""))
    }
    
    if st.button("Aktuelle Einstellungen speichern"):
        pname = profile_name_input.strip()
        if not pname:
            st.warning("Bitte einen Profilnamen eingeben.")
        else:
            save_current_settings(
                pname,
                profile_data.get("use_pubmed", True),
                profile_data.get("use_epmc", True),
                profile_data.get("use_google", False),
                profile_data.get("use_semantic", False),
                profile_data.get("use_openalex", False),
                profile_data.get("use_core", False),
                profile_data.get("use_chatgpt", False),
                sheet_choice if st.checkbox("Gene aus Excel verwenden", value=True) else "",
                profile_data.get("text_input", "")
            )

if __name__ == "__main__":
    module_codewords_pubmed()
