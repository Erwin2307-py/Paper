import streamlit as st
import requests
import openai
import pandas as pd
import os

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
    params = {"search": "test", "per-page": 1}
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
# 1a) Echte Semantic Scholar Suche (statt Dummy-Funktion)
##############################################################################

def search_semantic_scholar(query, limit=5):
    """
    Führt eine Suche in der Semantic Scholar API durch und gibt die Ergebnisse zurück.
    Parameter:
      query: Suchbegriff als String
      limit: Anzahl der zurückzugebenden Ergebnisse
    Rückgabe:
      Liste von Publikationen (als Dictionaries) oder leere Liste im Fehlerfall.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,abstract"
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Überprüft, ob die Anfrage erfolgreich war
        data = response.json()
        return data.get("data", [])
    except requests.RequestException as e:
        st.error(f"Fehler bei der Semantic Scholar Anfrage: {e}")
        return []

##############################################################################
# 2) Gene-Loader: Liest ab C3 einer gegebenen Sheet
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt Gene ab C3 (Spalte C, Zeile 3) im gewählten Sheet in 'genes.xlsx'.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        gene_series = df.iloc[2:, 2]  # ab Zeile 3, Spalte C
        gene_list = gene_series.dropna().astype(str).tolist()
        return gene_list
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 3) ChatGPT-Funktion zum Filtern
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
            line = line.strip()
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
# 4) Einstellungen speichern/laden (Profile)
##############################################################################

def save_current_settings(profile_name: str, 
                          use_pubmed: bool, 
                          use_epmc: bool, 
                          use_google: bool,
                          use_semantic: bool,
                          use_openalex: bool,
                          use_core: bool,
                          use_chatgpt: bool,
                          sheet_choice: str,
                          text_input: str):
    """
    Speichert die aktuellen Einstellungen in st.session_state["profiles"]
    unter dem Schlüssel = profile_name.
    """
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
    """
    Lädt die Einstellungen aus st.session_state["profiles"][profile_name]
    und gibt sie als Dict zurück.
    Wenn das Profil nicht existiert, None zurückgeben.
    """
    if "profiles" in st.session_state:
        profiles = st.session_state["profiles"]
        if profile_name in profiles:
            return profiles[profile_name]
    return None

##############################################################################
# 5) Haupt-Funktion für Streamlit
##############################################################################

def module_online_api_filter():
    """
    Kombiniert:
      A) API-Auswahl + Verbindungstest
      B) Gene-Filter (ab C3) via ChatGPT
      C) Settings-Speicherung (Profile) mit Name
      D) Gene nur auf Wunsch anzeigen (Checkbox)
      E) ChatGPT-Synonym-Fenster (Expander), wenn ChatGPT aktiviert
      F) Semantic Scholar Suche (echte API-Anbindung)
    """
    st.title("API-Auswahl & Gene-Filter mit Profile-Speicherung + ChatGPT-Synonym-Fenster")

    # ------------------------------------
    # Profilverwaltung
    # ------------------------------------
    st.subheader("Profilverwaltung")
    
    profile_name_input = st.text_input("Profilname eingeben (für Speichern/Laden):", "")
    existing_profiles = []
    if "profiles" in st.session_state:
        existing_profiles = list(st.session_state["profiles"].keys())
    selected_profile_to_load = st.selectbox("Oder wähle ein bestehendes Profil zum Laden:", ["(kein)"] + existing_profiles)
    load_profile_btn = st.button("Profil laden")

    # ------------------------------------
    # A) API-Auswahl (Checkboxen) + Verbindungstest
    # ------------------------------------
    st.subheader("A) API-Auswahl (Checkboxen) + Verbindungstest")

    col1, col2 = st.columns(2)
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

    # Profil Laden
    if load_profile_btn:
        if selected_profile_to_load != "(kein)":
            loaded = load_settings(selected_profile_to_load)
            if loaded:
                st.session_state["current_settings"].update(loaded)
                st.success(f"Profil '{selected_profile_to_load}' geladen.")
            else:
                st.warning(f"Profil '{selected_profile_to_load}' nicht gefunden.")
        else:
            st.info("Kein Profil zum Laden ausgewählt.")

    current = st.session_state["current_settings"]
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
            if check_pubmed_connection():
                dots_list.append(f"{green_dot()} <strong>PubMed</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>PubMed</strong>: FAIL")

        if use_epmc:
            if check_europe_pmc_connection():
                dots_list.append(f"{green_dot()} <strong>Europe PMC</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Europe PMC</strong>: FAIL")

        if use_google:
            if check_google_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Google Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Google Scholar</strong>: FAIL")

        if use_semantic:
            if check_semantic_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Semantic Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Semantic Scholar</strong>: FAIL")

        if use_openalex:
            if check_openalex_connection():
                dots_list.append(f"{green_dot()} <strong>OpenAlex</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>OpenAlex</strong>: FAIL")

        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            if check_core_connection(core_api_key):
                dots_list.append(f"{green_dot()} <strong>CORE</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>CORE</strong>: FAIL (Key nötig?)")

        if use_chatgpt:
            if check_chatgpt_connection():
                dots_list.append(f"{green_dot()} <strong>ChatGPT</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>ChatGPT</strong>: FAIL (API-Key nötig?)")

        if not dots_list:
            st.info("Keine Option ausgewählt.")
        else:
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)

    # ------------------------------------
    # E) ChatGPT-Synonym-Fenster (nur wenn ChatGPT True)
    # ------------------------------------
    if "synonyms_selected" not in st.session_state:
        st.session_state["synonyms_selected"] = {
            "genotype": False,
            "phenotype": False,
            "snp": False,
            "inc_dec": False
        }

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

            synonyms_local["genotype"] = genotype_check
            synonyms_local["phenotype"] = phenotype_check
            synonyms_local["snp"]       = snp_check
            synonyms_local["inc_dec"]   = inc_dec_check

    # ------------------------------------
    # B) Gene-Filter-Bereich
    # ------------------------------------
    st.write("---")
    st.subheader("B) Gene-Filter via ChatGPT (ab C3)")

    st.write(
        "Wähle ein Sheet aus `modules/genes.xlsx` (ab Spalte C, Zeile 3). "
        "Wenn gewünscht, kannst du via Checkbox die Gene anzeigen. "
        "Danach einen Text eingeben. ChatGPT prüft, ob die Gene erwähnt sind."
    )

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

    current_sheet = current["sheet_choice"]
    if current_sheet not in sheet_names:
        current_sheet = sheet_names[0]

    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names, 
                                index=sheet_names.index(current_sheet) if current_sheet in sheet_names else 0)

    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)

    show_genes = st.checkbox("Gene-Liste anzeigen?", value=False)
    if show_genes and genes:
        st.markdown(f"**Gelistete Gene** in Sheet '{sheet_choice}' (ab C3):")
        st.write(genes)

    st.write("---")
    st.subheader("Text eingeben (z. B. Abstract)")

    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", height=200, value=current["text_input"])

    if st.button("Gene filtern mit ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder das Sheet ist leer.")
        elif not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
        else:
            extended_genes = list(genes)
            synset = st.session_state["synonyms_selected"]
            if synset["genotype"]:
                extended_genes += ["genetic makeup", "genetic constitution", "AllEl", "DNA sequence"]
            if synset["phenotype"]:
                extended_genes += ["observable traits", "physical appearance", "morphology"]
            if synset["snp"]:
                extended_genes += ["point mutation", "genetic variation", "DNA polymorphism"]
            if synset["inc_dec"]:
                extended_genes += ["increase", "decrease"]

            result_map = check_genes_in_text_with_chatgpt(text_input, extended_genes)
            if not result_map:
                st.info("Keine Ergebnisse oder Fehler aufgetreten.")
            else:
                st.markdown("### Ergebnis (inkl. Synonyme):")
                for g in extended_genes:
                    found = result_map.get(g, False)
                    if found:
                        st.write(f"**{g}**: YES")
                    else:
                        st.write(f"{g}: No")

    # ------------------------------------
    # F) Semantic Scholar Suche (echte API-Anbindung)
    # ------------------------------------
    if use_semantic:
        st.write("---")
        st.subheader("F) Semantic Scholar Suche")
        sem_query = st.text_input("Semantic Scholar Suchbegriff:", "")
        sem_limit = st.number_input("Anzahl Ergebnisse", min_value=1, max_value=20, value=5, step=1)
        if st.button("Semantic Scholar durchsuchen"):
            if not sem_query.strip():
                st.warning("Bitte einen Suchbegriff eingeben.")
            else:
                sem_results = search_semantic_scholar(sem_query, limit=sem_limit)
                if not sem_results:
                    st.info("Keine Ergebnisse gefunden oder Fehler bei der Anfrage.")
                else:
                    st.markdown(f"### Ergebnisse für '{sem_query}':")
                    for paper in sem_results:
                        title = paper.get("title", "Kein Titel verfügbar")
                        authors = paper.get("authors", [])
                        # Autoren: Liste von Dictionaries, z. B. {'name': 'Autor Name'}
                        author_names = ", ".join(author.get("name", "") for author in authors)
                        year = paper.get("year", "Kein Jahr verfügbar")
                        abstract = paper.get("abstract", "Kein Abstract verfügbar")
                        st.markdown(f"**Titel:** {title}")
                        st.markdown(f"**Autoren:** {author_names}")
                        st.markdown(f"**Jahr:** {year}")
                        st.markdown(f"**Abstract:** {abstract}")
                        st.write("---")

    st.write("---")
    st.info(
        "Fertig. Du kannst oben die APIs auswählen und testen, sowie Profile speichern/laden. "
        "Die Gene werden ab C3 eingelesen und nur angezeigt, wenn du es anforderst. "
        "Wenn ChatGPT aktiv ist, kannst du im Expander Synonyme auswählen."
    )

    st.session_state["current_settings"] = {
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

    if st.button("Aktuelle Einstellungen speichern"):
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
                sheet_choice,
                text_input
            )

if __name__ == "__main__":
    module_online_api_filter()
