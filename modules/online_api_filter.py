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
        _ = next(search_results)  # 1 Ergebnis abrufen
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
# 2) Gene-Loader: Liest ab C3 einer gegebenen Sheet
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt Gene ab C3 (Spalte C, Zeile 3) im gewählten Sheet in 'genes.xlsx'.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        # Ab Zeile 3 (Index=2), Spalte C (Index=2)
        gene_series = df.iloc[2:, 2]
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
# 4) Haupt-Funktion für Streamlit
##############################################################################

def module_online_api_filter():
    """
    Kombiniert:
      A) API-Auswahl + Verbindungstest
      B) Gene-Filter (ab C3) via ChatGPT
      C) Speichere-Button für Gene-Filter-Ergebnisse
    """
    st.title("API-Auswahl & Gene-Filter (ab C3) + 'Speichere'-Button")

    # ------------------------------------
    # A) API-Auswahl
    # ------------------------------------
    st.subheader("A) API-Auswahl (Checkboxen) + Verbindungstest")

    col1, col2 = st.columns(2)

    # Session State Defaults
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

    with col1:
        use_pubmed = st.checkbox("PubMed", value=st.session_state["use_pubmed"])
        use_epmc = st.checkbox("Europe PMC", value=st.session_state["use_epmc"])
        use_google = st.checkbox("Google Scholar", value=st.session_state["use_google"])
        use_semantic = st.checkbox("Semantic Scholar", value=st.session_state["use_semantic"])

    with col2:
        use_openalex = st.checkbox("OpenAlex", value=st.session_state["use_openalex"])
        use_core = st.checkbox("CORE", value=st.session_state["use_core"])
        use_chatgpt = st.checkbox("ChatGPT", value=st.session_state["use_chatgpt"])

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
            st.info("Keine API ausgewählt.")
        else:
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)

    # Zustand aktualisieren
    st.session_state["use_pubmed"] = use_pubmed
    st.session_state["use_epmc"] = use_epmc
    st.session_state["use_google"] = use_google
    st.session_state["use_semantic"] = use_semantic
    st.session_state["use_openalex"] = use_openalex
    st.session_state["use_core"] = use_core
    st.session_state["use_chatgpt"] = use_chatgpt

    # ------------------------------------
    # B) Gene-Filter-Bereich
    # ------------------------------------
    st.write("---")
    st.subheader("B) Gene-Filter via ChatGPT (ab C3) mit Speichere-Button")

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

    # Session State: gewähltes Sheet und Text
    if "sheet_choice" not in st.session_state:
        st.session_state["sheet_choice"] = sheet_names[0]
    if "text_input" not in st.session_state:
        st.session_state["text_input"] = ""

    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names,
                                index=sheet_names.index(st.session_state["sheet_choice"])
                                if st.session_state["sheet_choice"] in sheet_names else 0)

    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)
        st.write(f"**Gelistete Gene** in Sheet '{sheet_choice}' (ab C3):")
        st.write(genes)

    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", 
                              height=200, 
                              value=st.session_state["text_input"])

    # Hier halten wir das Ergebnis in st.session_state
    if "gene_filter_result" not in st.session_state:
        st.session_state["gene_filter_result"] = {}

    if st.button("Gene filtern mit ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder das Sheet ist leer.")
        elif not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
        else:
            result_map = check_genes_in_text_with_chatgpt(text_input, genes)
            if not result_map:
                st.info("Keine Ergebnisse oder Fehler aufgetreten.")
            else:
                st.session_state["gene_filter_result"] = result_map
                st.markdown("### Ergebnis:")
                for g in genes:
                    found = result_map.get(g, False)
                    if found:
                        st.write(f"**{g}**: YES")
                    else:
                        st.write(f"{g}: No")

    # SPEICHERE-BUTTON FÜR GENE-FILTER-ERGEBNIS
    def save_gene_filter_results():
        # Hier könntest du sie ggf. in einer Datei oder DB speichern.
        # Für die Demo speichern wir einfach in st.session_state "saved_gene_results"
        st.session_state["saved_gene_results"] = st.session_state["gene_filter_result"]
        st.success("Gene-Filter-Ergebnisse wurden gespeichert (in session_state).")

    st.button("Speichere Gene-Filter-Ergebnisse", on_click=save_gene_filter_results)

    # Zustand aktualisieren
    st.session_state["sheet_choice"] = sheet_choice
    st.session_state["text_input"] = text_input

    st.write("---")
    st.info(
        "Fertig. Oben kannst du APIs auswählen und testen, hier Gene filtern. "
        "Außerdem kannst du das Ergebnis per Button 'Speichere Gene-Filter-Ergebnisse' in session_state speichern."
    )

    # Optional: anzeigen, ob wir schon gespeicherte Ergebnisse haben
    if "saved_gene_results" in st.session_state:
        st.write("Bereits gespeicherte Ergebnisse:", st.session_state["saved_gene_results"])
