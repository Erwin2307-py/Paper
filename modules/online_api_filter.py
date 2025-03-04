import streamlit as st
import requests
import openai
import pandas as pd
import os

##############################################################################
# 1) Verbindungstest-Funktionen für diverse APIs
##############################################################################

def check_pubmed_connection(timeout=5):
    """
    Prüft Verbindung zu PubMed (vereinfacht).
    """
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
    """
    Prüft Verbindung zu Europe PMC (vereinfacht).
    """
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
    """
    Prüft Verbindung zu Google Scholar, indem eine kurze Testsuche gemacht wird.
    Erfordert 'scholarly' installiert.
    """
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs("test")
        _ = next(search_results)  # 1 Ergebnis abrufen
        return True
    except Exception:
        return False

def check_semantic_scholar_connection(timeout=5):
    """
    Prüft Verbindung zu Semantic Scholar (API).
    """
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
    """
    Prüft Verbindung zu OpenAlex.
    """
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
    """
    Prüft Verbindung zu CORE. 
    Benötigt CORE_API_KEY in st.secrets["CORE_API_KEY"] oder Übergabe als Parameter.
    """
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
    """
    Prüft Verbindung zu ChatGPT (OpenAI). Benötigt OPENAI_API_KEY in st.secrets["OPENAI_API_KEY"].
    """
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
# 2) Gene-Loader: Liest ab C3 einer gegebenen Sheet
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt Gene ab Zelle C3 (Spalte C, Zeile 3) aus dem gewählten Sheet in `modules/genes.xlsx`.
    
    Annahmen:
      - 'genes.xlsx' liegt direkt im Ordner 'modules'.
      - In Spalte C (Index=2) ab Zeile 3 (Index=2) stehen die Gene.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        # df.iloc[2:, 2] => Ab Zeile 3 (0-basiert=2), Spalte C (0-basiert=2)
        gene_series = df.iloc[2:, 2]
        # NaN entfernen + in String umwandeln
        gene_list = gene_series.dropna().astype(str).tolist()
        return gene_list
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 3) ChatGPT-Funktion zum Filtern
##############################################################################

def check_genes_in_text_with_chatgpt(text: str, genes: list, model="gpt-3.5-turbo") -> dict:
    """
    Fragt ChatGPT, ob die gegebenen 'genes' im 'text' thematisch erwähnt werden.
    Gibt ein Dict {GenA: True, GenB: False, ...} zurück.
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY']!")
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
        f"Antworte zeilenweise in der Form:\n"
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
      A) API-Auswahl (PubMed, Europe PMC, Google Scholar, Semantic Scholar,
         OpenAlex, CORE, ChatGPT) + Verbindungstest
      B) Gene-Filter: ab C3 eines Sheets in 'genes.xlsx', 
         ChatGPT-Abfrage, ob diese Gene im eingegebenen Text vorkommen.
    """
    st.title("API-Auswahl & Gene-Filter (ab C3) mit ChatGPT")

    # ------------------------------------------------------
    # A) API-Verbindungschecks
    # ------------------------------------------------------
    st.subheader("A) API-Verbindungschecks")

    col1, col2 = st.columns(2)
    with col1:
        use_pubmed = st.checkbox("PubMed", value=True)
        use_epmc = st.checkbox("Europe PMC", value=True)
        use_google = st.checkbox("Google Scholar", value=False)
        use_semantic = st.checkbox("Semantic Scholar", value=False)

    with col2:
        use_openalex = st.checkbox("OpenAlex", value=False)
        use_core = st.checkbox("CORE", value=False)
        use_chatgpt = st.checkbox("ChatGPT", value=False)

    if st.button("Verbindung prüfen"):
        def green_dot():
            return "<span style='color: limegreen; font-size: 20px;'>&#9679;</span>"
        def red_dot():
            return "<span style='color: red; font-size: 20px;'>&#9679;</span>"

        dots_list = []

        # PubMed
        if use_pubmed:
            if check_pubmed_connection():
                dots_list.append(f"{green_dot()} <strong>PubMed</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>PubMed</strong>: FAIL")

        # Europe PMC
        if use_epmc:
            if check_europe_pmc_connection():
                dots_list.append(f"{green_dot()} <strong>Europe PMC</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Europe PMC</strong>: FAIL")

        # Google Scholar
        if use_google:
            if check_google_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Google Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Google Scholar</strong>: FAIL")

        # Semantic Scholar
        if use_semantic:
            if check_semantic_scholar_connection():
                dots_list.append(f"{green_dot()} <strong>Semantic Scholar</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>Semantic Scholar</strong>: FAIL")

        # OpenAlex
        if use_openalex:
            if check_openalex_connection():
                dots_list.append(f"{green_dot()} <strong>OpenAlex</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>OpenAlex</strong>: FAIL")

        # CORE
        if use_core:
            core_api_key = st.secrets.get("CORE_API_KEY", "")
            if check_core_connection(core_api_key):
                dots_list.append(f"{green_dot()} <strong>CORE</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>CORE</strong>: FAIL (Key nötig?)")

        # ChatGPT
        if use_chatgpt:
            if check_chatgpt_connection():
                dots_list.append(f"{green_dot()} <strong>ChatGPT</strong>: OK")
            else:
                dots_list.append(f"{red_dot()} <strong>ChatGPT</strong>: FAIL (API-Key nötig?)")

        if not dots_list:
            st.info("Keine Option ausgewählt.")
        else:
            st.markdown(" &nbsp;&nbsp;&nbsp; ".join(dots_list), unsafe_allow_html=True)

    # ------------------------------------------------------
    # B) Gene-Filter-Bereich
    # ------------------------------------------------------
    st.write("---")
    st.subheader("B) Gene-Filter mit ChatGPT (ab C3)")

    st.write(
        "Wähle ein Sheet aus `modules/genes.xlsx`, ab Spalte C, Zeile 3. "
        "Danach kannst du einen Text (Paper-Abstract) eingeben. "
        "ChatGPT prüft, ob diese Gene erwähnt werden."
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

    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names)

    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)
        st.write(f"**Gelistete Gene** in Sheet '{sheet_choice}' (ab C3):")
        st.write(genes)

    st.write("---")
    st.subheader("Text eingeben (z. B. Abstract)")

    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", height=200)

    if st.button("Gene filtern mit ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder Sheet ist leer.")
            return
        if not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
            return

        result_map = check_genes_in_text_with_chatgpt(text_input, genes)
        if not result_map:
            st.info("Keine Ergebnisse oder Fehler aufgetreten.")
            return

        st.markdown("### Ergebnis:")
        for g in genes:
            found = result_map.get(g, False)
            if found:
                st.write(f"**{g}**: YES")
            else:
                st.write(f"{g}: No")

    st.write("---")
    st.info(
        "Fertig. Oben kannst du die APIs aktivieren und testen, "
        "und hier kannst du die Gene analysieren. "
        "Die Gene werden ab C3 eingelesen."
    )
