import streamlit as st
import requests
import openai
import pandas as pd
import os
import time

##############################################################################
# 1) Verbindungstest-Funktionen für diverse APIs
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
            messages=[{"role":"user", "content":"Short connectivity test. Reply with any short message."}],
            max_tokens=10,
            temperature=0
        )
        return True
    except Exception:
        return False

##############################################################################
# 2) API-Suchfunktionen
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

##############################################################################
# CORE Aggregate API (echte API-Anbindung)
##############################################################################

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
# 6) Haupt-Modul: Online API Filter & Gene-Filter
##############################################################################

def module_online_api_filter():
    st.title("API-Auswahl & Gene-Filter mit Profile-Speicherung + ChatGPT-Synonym-Fenster")

    # Profilverwaltung
    st.subheader("Profilverwaltung")
    profile_name_input = st.text_input("Profilname eingeben (für Speichern/Laden):", "")
    existing_profiles = list(st.session_state.get("profiles", {}).keys())
    selected_profile_to_load = st.selectbox("Oder wähle ein bestehendes Profil zum Laden:", ["(kein)"] + existing_profiles)
    load_profile_btn = st.button("Profil laden")
    if load_profile_btn:
        if selected_profile_to_load != "(kein)":
            loaded = load_settings(selected_profile_to_load)
            if loaded:
                st.session_state["current_settings"] = loaded
                st.success(f"Profil '{selected_profile_to_load}' geladen.")
            else:
                st.warning(f"Profil '{selected_profile_to_load}' nicht gefunden.")
        else:
            st.info("Kein Profil zum Laden ausgewählt.")

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
            "text_input": ""
        }
    current = st.session_state["current_settings"]

    # API-Auswahl & Verbindungstest
    st.subheader("A) API-Auswahl (Checkboxen) + Verbindungstest")
    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=current["use_pubmed"])
        use_epmc = st.checkbox("Europe PMC", value=current["use_epmc"])
        use_google = st.checkbox("Google Scholar", value=current["use_google"])
        use_semantic = st.checkbox("Semantic Scholar", value=current["use_semantic"])
    with col2:
        use_openalex = st.checkbox("OpenAlex", value=current["use_openalex"])
        use_core = st.checkbox("CORE", value=current["use_core"])
        use_chatgpt = st.checkbox("ChatGPT", value=current["use_chatgpt"])

    if st.button("Verbindung prüfen"):
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"
        dots_list = []
        if use_pubmed:
            dots_list.append(f"{green_dot() if check_pubmed_connection() else red_dot()} <strong>PubMed</strong>")
        if use_epmc:
            dots_list.append(f"{green_dot() if check_europe_pmc_connection() else red_dot()} <strong>Europe PMC</strong>")
        if use_google:
            dots_list.append(f"{green_dot() if check_google_scholar_connection() else red_dot()} <strong>Google Scholar</strong>")
        if use_semantic:
            dots_list.append(f"{green_dot() if check_semantic_scholar_connection() else red_dot()} <strong>Semantic Scholar</strong>")
        if use_openalex:
            dots_list.append(f"{green_dot() if check_openalex_connection() else red_dot()} <strong>OpenAlex</strong>")
        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            dots_list.append(f"{green_dot() if check_core_connection(core_api_key) else red_dot()} <strong>CORE</strong>")
        if use_chatgpt:
            dots_list.append(f"{green_dot() if check_chatgpt_connection() else red_dot()} <strong>ChatGPT</strong>")
        st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)

    # ChatGPT-Synonym-Fenster
    if "synonyms_selected" not in st.session_state:
        st.session_state["synonyms_selected"] = {"genotype": False, "phenotype": False, "snp": False, "inc_dec": False}
    synonyms_local = st.session_state["synonyms_selected"]
    if use_chatgpt:
        with st.expander("ChatGPT: Begriffe & Synonyme auswählen"):
            st.markdown("""
**Genotyp**  
Deutsch: Erbbild, genetische Ausstattung, genetisches Profil  
Englisch: genotype, genetic makeup, genetic constitution  
Verwandte Begriffe: Allel, Genom, DNA-Sequenz
""")
            genotype_check = st.checkbox("Genotyp (inkl. Synonyme)", value=synonyms_local["genotype"])
            st.markdown("""
**Phänotyp**  
Deutsch: Erscheinungsbild, äußeres Merkmal, Merkmalsausprägung  
Englisch: phenotype, observable traits, physical appearance  
Verwandte Begriffe: Morphologie, physiologische Eigenschaften, Verhalten
""")
            phenotype_check = st.checkbox("Phänotyp (inkl. Synonyme)", value=synonyms_local["phenotype"])
            st.markdown("""
**Single Nucleotide Polymorphism (SNP)**  
Deutsch: Einzelnukleotid-Polymorphismus, Punktmutation  
Englisch: Single Nucleotide Polymorphism (SNP), point mutation  
Verwandte Begriffe: genetische Variation, DNA-Polymorphismus
""")
            snp_check = st.checkbox("SNP (inkl. Synonyme)", value=synonyms_local["snp"])
            inc_dec_check = st.checkbox("Increase/Decrease (auch das Gegenteil suchen?)", value=synonyms_local["inc_dec"])
            synonyms_local.update({"genotype": genotype_check, "phenotype": phenotype_check, "snp": snp_check, "inc_dec": inc_dec_check})

    # Gene-Filter-Bereich
    st.write("---")
    st.subheader("B) Gene-Filter via ChatGPT (ab C3)")
    st.write("Wähle ein Sheet aus `modules/genes.xlsx` (ab Spalte C, Zeile 3) und entscheide per Häkchen, ob die Gene aus der Excel-Liste verwendet werden sollen.")
    
    use_gene_list = st.checkbox("Gene aus Excel verwenden", value=True)
    
    genes = []
    if use_gene_list:
        excel_path = os.path.join("modules", "genes.xlsx")
        if not os.path.exists(excel_path):
            st.error("Die Datei 'genes.xlsx' wurde nicht in 'modules/' gefunden!")
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
        sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names, index=sheet_names.index(current_sheet))
        genes = load_genes_from_excel(sheet_choice)
    else:
        st.info("Gene werden nicht aus Excel geladen.")

    show_genes = st.checkbox("Gene-Liste anzeigen?", value=False)
    if show_genes and genes:
        st.markdown(f"**Gelistete Gene** (ab C3):")
        st.write(genes)

    st.write("---")
    st.subheader("Text eingeben (z. B. Abstract)")
    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", height=200, value=current.get("text_input", ""))
    
    if st.button("Gene filtern mit ChatGPT"):
        if use_gene_list and not genes:
            st.warning("Keine Gene geladen oder das Sheet ist leer.")
        elif not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
        else:
            extended_genes = list(genes) if use_gene_list else []
            if synonyms_local["genotype"]:
                extended_genes += ["genetic makeup", "genetic constitution", "AllEl", "DNA sequence"]
            if synonyms_local["phenotype"]:
                extended_genes += ["observable traits", "physical appearance", "morphology"]
            if synonyms_local["snp"]:
                extended_genes += ["point mutation", "genetic variation", "DNA polymorphism"]
            if synonyms_local["inc_dec"]:
                extended_genes += ["increase", "decrease"]
            if not extended_genes:
                st.info("Keine Gene zum Filtern vorhanden.")
            else:
                result_map = check_genes_in_text_with_chatgpt(text_input, extended_genes)
                if not result_map:
                    st.info("Keine Ergebnisse oder Fehler aufgetreten.")
                else:
                    st.markdown("### Ergebnis (inkl. Synonyme):")
                    for gene in extended_genes:
                        st.write(f"**{gene}**: {'YES' if result_map.get(gene, False) else 'No'}")

    # F) Semantic Scholar Suche
    if use_semantic:
        st.write("---")
        st.subheader("F) Semantic Scholar Suche")
        sem_query = st.text_input("Semantic Scholar Suchbegriff:", key="sem_query")
        sem_limit = st.number_input("Anzahl Ergebnisse", min_value=1, max_value=20, value=5, step=1, key="sem_limit")
        if st.button("Semantic Scholar durchsuchen"):
            if not sem_query.strip():
                st.warning("Bitte einen Suchbegriff eingeben.")
            else:
                sem_results = search_semantic_scholar(sem_query, max_results=sem_limit)
                if not sem_results:
                    st.info("Keine Ergebnisse gefunden oder Fehler bei der Anfrage.")
                else:
                    st.markdown(f"### Ergebnisse für '{sem_query}':")
                    for paper in sem_results:
                        title = paper.get("title", "Kein Titel verfügbar")
                        authors = paper.get("authors", [])
                        author_names = ", ".join(author.get("name", "") for author in authors)
                        year = paper.get("year", "Kein Jahr verfügbar")
                        abstract = paper.get("abstract", "Kein Abstract verfügbar")
                        st.markdown(f"**Titel:** {title}")
                        st.markdown(f"**Autoren:** {author_names}")
                        st.markdown(f"**Jahr:** {year}")
                        st.markdown(f"**Abstract:** {abstract}")
                        st.write("---")

    # G) Google Scholar Suche
    if use_google:
        st.write("---")
        st.subheader("G) Google Scholar Suche")
        gs_query = st.text_input("Google Scholar Suchbegriff:", key="gs_query")
        gs_limit = st.number_input("Anzahl Ergebnisse", min_value=1, max_value=20, value=5, step=1, key="gs_limit")
        if st.button("Google Scholar durchsuchen"):
            if not gs_query.strip():
                st.warning("Bitte einen Suchbegriff eingeben.")
            else:
                gs_results = search_google_scholar(gs_query, max_results=gs_limit)
                if not gs_results:
                    st.info("Keine Ergebnisse gefunden oder Fehler bei der Anfrage.")
                else:
                    st.markdown(f"### Ergebnisse für '{gs_query}':")
                    for paper in gs_results:
                        title = paper.get("Title", "Kein Titel verfügbar")
                        year = paper.get("Year", "Kein Jahr verfügbar")
                        st.markdown(f"**Titel:** {title}")
                        st.m
