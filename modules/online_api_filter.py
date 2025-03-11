import streamlit as st
import requests
import openai
import pandas as pd
import os

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
        # Kleiner Test, 1 Result abfragen:
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
            messages=[{"role": "user", "content": "Short connectivity test."}],
            max_tokens=10,
            temperature=0
        )
        return True
    except Exception:
        return False

##############################################################################
# 2) CORE-API-Beispiel (optional)
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

def search_core(query: str, max_results=10):
    core_api_key = st.secrets.get("CORE_API_KEY", "")
    if not core_api_key:
        st.error("CORE API Key fehlt! Bitte in st.secrets['CORE_API_KEY'] hinterlegen.")
        return []
    core_api = CoreAPI(core_api_key)
    try:
        result = core_api.search_publications(query, limit=max_results)
        pubs = result.get("results", [])
        transformed = []
        for pub in pubs:
            transformed.append({
                "Source": "CORE",
                "Title": pub.get("title", "n/a"),
                "PubMed ID": "n/a",
                "DOI": pub.get("doi", "n/a"),
                "Year": pub.get("publicationDate", "n/a"),
                "Abstract": "n/a",
                "Population": "n/a"
            })
        return transformed
    except Exception as e:
        st.error(f"CORE API Anfrage fehlgeschlagen: {e}")
        return []

##############################################################################
# 3) Gene-Loader
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Liest ab Zeile 3 (Index 2), Spalte C (Index 2) die Gene ein.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    if not os.path.exists(excel_path):
        st.error("Die Datei 'genes.xlsx' wurde nicht unter 'modules/' gefunden!")
        return []
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        gene_series = df.iloc[2:, 2]
        return gene_series.dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 4) ChatGPT-Funktion: Genes im Text filtern
##############################################################################

def check_genes_in_text_with_chatgpt(text: str, genes: list, model="gpt-3.5-turbo") -> dict:
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY']!")
        return {}
    if not text.strip():
        st.warning("Kein Text eingegeben.")
        return {}
    if not genes:
        st.info("Keine Gene oder Synonyme vorhanden.")
        return {}

    joined_genes = ", ".join(genes)
    prompt = (
        f"Hier ist ein Text:\n\n{text}\n\n"
        f"Hier eine Liste von Genen/Synonymen: {joined_genes}\n"
        f"Gib für jedes an, ob es im Text vorkommt (Yes) oder nicht (No). "
        f"Antwortformat:\nGENE: Yes\nGENE2: No\n"
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
# 5) Profilverwaltung
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
    """Speichert alle relevanten Einstellungen in st.session_state."""
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
        "text_input": text_input,

        # Erweiterte Felder:
        "selected_genes": st.session_state.get("selected_genes", []),
        "synonyms_selected": st.session_state.get("synonyms_selected", {}),
        "final_gene": st.session_state.get("final_gene", ""),
        "codewords_str": st.session_state.get("codewords_str", "")
    }
    st.success(f"Profil '{profile_name}' erfolgreich gespeichert.")

def load_settings(profile_name: str):
    """Auslesen eines gespeicherten Profils (falls vorhanden)."""
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
    return None

##############################################################################
# 6) Erstes Modul: Online API Filter & Gene-Filter
##############################################################################

def module_online_api_filter():
    st.title("Modul 1: API-Auswahl & Gene-Filter mit Profile-Speicherung")

    # Profilverwaltung: Laden
    st.subheader("Profilverwaltung")
    profile_name_input = st.text_input("Profilname (zum Speichern):", "")
    existing_profiles = list(st.session_state.get("profiles", {}).keys())
    selected_profile_to_load = st.selectbox("Profil laden:", ["(kein)"] + existing_profiles)
    if st.button("Ausgewähltes Profil laden"):
        if selected_profile_to_load != "(kein)":
            loaded = load_settings(selected_profile_to_load)
            if loaded:
                st.success(f"Profil '{selected_profile_to_load}' geladen.")
                # Wiederherstellen:
                st.session_state["selected_genes"] = loaded.get("selected_genes", [])
                st.session_state["synonyms_selected"] = loaded.get("synonyms_selected", {})
                st.session_state["final_gene"] = loaded.get("final_gene", "")
                st.session_state["codewords_str"] = loaded.get("codewords_str", "")
                st.session_state["use_pubmed"] = loaded.get("use_pubmed", True)
                st.session_state["use_epmc"] = loaded.get("use_epmc", True)
                st.session_state["use_google"] = loaded.get("use_google", False)
                st.session_state["use_semantic"] = loaded.get("use_semantic", False)
                st.session_state["use_openalex"] = loaded.get("use_openalex", False)
                st.session_state["use_core"] = loaded.get("use_core", False)
                st.session_state["use_chatgpt"] = loaded.get("use_chatgpt", False)
                st.session_state["sheet_choice"] = loaded.get("sheet_choice", "")
                st.session_state["text_input"] = loaded.get("text_input", "")
        else:
            st.info("Kein Profil gewählt.")

    # Default-Flags
    if "use_pubmed" not in st.session_state:
        st.session_state["use_pubmed"] = True
    if "use_epmc" not in st.session_state:
        st.session_state["use_epmc"] = True
    if "use_google" not in st.session_state:
        st.session_state["use_google"] = False
    if "use_semantic" not in st.session_state:
        st.session_state["use_semantic"] = False
    if "use_openalex" not in st.session_state:
        st.session_state["use_openalex"] = False
    if "use_core" not in st.session_state:
        st.session_state["use_core"] = False
    if "use_chatgpt" not in st.session_state:
        st.session_state["use_chatgpt"] = False
    if "synonyms_selected" not in st.session_state:
        st.session_state["synonyms_selected"] = {"genotype": False, "phenotype": False, "snp": False, "inc_dec": False}
    if "codewords_str" not in st.session_state:
        st.session_state["codewords_str"] = ""

    st.subheader("A) API-Auswahl + Verbindungstest")
    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=st.session_state["use_pubmed"])
        use_epmc = st.checkbox("Europe PMC", value=st.session_state["use_epmc"])
        use_google = st.checkbox("Google Scholar", value=st.session_state["use_google"])
        use_semantic = st.checkbox("Semantic Scholar", value=st.session_state["use_semantic"])
    with col2:
        use_openalex = st.checkbox("OpenAlex", value=st.session_state["use_openalex"])
        use_core = st.checkbox("CORE", value=st.session_state["use_core"])
        use_chatgpt = st.checkbox("ChatGPT (z.B. für Gene-Check)", value=st.session_state["use_chatgpt"])

    if st.button("Verbindungen testen"):
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"
        results = []
        if use_pubmed:
            results.append(f"{green_dot() if check_pubmed_connection() else red_dot()} PubMed")
        if use_epmc:
            results.append(f"{green_dot() if check_europe_pmc_connection() else red_dot()} Europe PMC")
        if use_google:
            results.append(f"{green_dot() if check_google_scholar_connection() else red_dot()} Google Scholar")
        if use_semantic:
            results.append(f"{green_dot() if check_semantic_scholar_connection() else red_dot()} Semantic Scholar")
        if use_openalex:
            results.append(f"{green_dot() if check_openalex_connection() else red_dot()} OpenAlex")
        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            results.append(f"{green_dot() if check_core_connection(core_api_key) else red_dot()} CORE")
        if use_chatgpt:
            results.append(f"{green_dot() if check_chatgpt_connection() else red_dot()} ChatGPT")

        st.markdown(" &nbsp;&nbsp;&nbsp; ".join(results), unsafe_allow_html=True)

    # ChatGPT-Synonym-Fenster
    if use_chatgpt:
        with st.expander("ChatGPT: Zusätzliche Synonyme auswählen"):
            st.markdown("""**Genotyp** (genotype, genetic makeup, ...)""")
            genotype_check = st.checkbox("Genotyp (Synonyme)", value=st.session_state["synonyms_selected"]["genotype"])
            st.markdown("""**Phänotyp** (phenotype, observable traits, ...)""")
            phenotype_check = st.checkbox("Phänotyp (Synonyme)", value=st.session_state["synonyms_selected"]["phenotype"])
            st.markdown("""**SNP** (Single Nucleotide Polymorphism, point mutation, ...)""")
            snp_check = st.checkbox("SNP (Synonyme)", value=st.session_state["synonyms_selected"]["snp"])
            inc_dec_check = st.checkbox("Increase/Decrease (auch Gegenteil)", value=st.session_state["synonyms_selected"]["inc_dec"])

            st.session_state["synonyms_selected"] = {
                "genotype": genotype_check,
                "phenotype": phenotype_check,
                "snp": snp_check,
                "inc_dec": inc_dec_check
            }

    st.write("---")
    st.subheader("B) Gene-Filter & -Auswahl")

    excel_path = os.path.join("modules", "genes.xlsx")
    if not os.path.exists(excel_path):
        st.error("Keine 'genes.xlsx' unter 'modules/' gefunden!")
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

    # Previously chosen sheet (if in session)
    current_sheet = st.session_state.get("sheet_choice", sheet_names[0])
    if current_sheet not in sheet_names:
        current_sheet = sheet_names[0]

    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names, index=sheet_names.index(current_sheet))
    all_genes_in_sheet = load_genes_from_excel(sheet_choice)

    if all_genes_in_sheet:
        unique_first_letters = sorted(list(set(g[0].upper() for g in all_genes_in_sheet if g.strip())))
        selected_letter = st.selectbox("Anfangsbuchstabe:", ["Alle"] + unique_first_letters)
        if selected_letter == "Alle":
            filtered_genes = all_genes_in_sheet
        else:
            filtered_genes = [g for g in all_genes_in_sheet if g and g[0].upper() == selected_letter]

        if filtered_genes:
            selected_gene = st.selectbox("Wähle 1 Gen aus:", filtered_genes)
        else:
            st.info("Keine Gene mit diesem Anfangsbuchstaben vorhanden.")
            selected_gene = ""
    else:
        st.warning("Keine Gene in diesem Sheet.")
        selected_gene = ""

    custom_gene_input = st.text_input("Eigenes Gen eingeben (optional):", "")
    final_gene = custom_gene_input.strip() if custom_gene_input.strip() else selected_gene.strip()
    st.session_state["final_gene"] = final_gene

    st.write("---")
    st.subheader("C) Codewörter & Test-Text")
    codewords_input = st.text_input("Codewörter (z.B. 'disease', 'drug', etc.):",
                                    value=st.session_state.get("codewords_str", ""))
    st.session_state["codewords_str"] = codewords_input

    text_input = st.text_area("Hier ein Text eingeben (z.B. Abstract) für ChatGPT-Test:",
                              height=200,
                              value=st.session_state.get("text_input", ""))
    st.session_state["text_input"] = text_input

    if st.button("Gene-Check mit ChatGPT"):
        if not use_chatgpt:
            st.warning("ChatGPT ist nicht aktiviert (Checkbox).")
            return
        if not final_gene:
            st.warning("Kein Gen ausgewählt/eingegeben.")
        elif not text_input.strip():
            st.warning("Kein Text eingegeben.")
        else:
            # Zusätzliche Synonyme anhängen
            gene_list = [final_gene]
            syns = st.session_state["synonyms_selected"]
            if syns.get("genotype"):
                gene_list += ["genetic makeup", "genetic constitution", "DNA sequence", "Allele"]
            if syns.get("phenotype"):
                gene_list += ["observable traits", "physical appearance", "morphology"]
            if syns.get("snp"):
                gene_list += ["point mutation", "genetic variation", "DNA polymorphism"]
            if syns.get("inc_dec"):
                gene_list += ["increase", "decrease"]

            st.session_state["selected_genes"] = gene_list

            result_map = check_genes_in_text_with_chatgpt(text_input, gene_list)
            if result_map:
                st.markdown("### Ergebnis (Gene-Check):")
                for gene_key, status in result_map.items():
                    st.write(f"- **{gene_key}**: {'Yes' if status else 'No'}")
            else:
                st.info("Keine Ergebnisse oder ChatGPT-Fehler.")

    st.write("---")
    if st.button("Einstellungen als Profil speichern"):
        pname = profile_name_input.strip()
        if not pname:
            st.warning("Bitte Profilnamen eingeben.")
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

def main():
    st.set_page_config(layout="wide")
    module_online_api_filter()

if __name__ == "__main__":
    main()
