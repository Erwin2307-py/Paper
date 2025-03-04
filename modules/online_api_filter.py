# modules/online_api_filter.py

import streamlit as st
import requests
import openai
import pandas as pd
import os

##############################################################################
# 1) Verbindungstest-Funktionen
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
    Prüft Verbindung zu Google Scholar, indem eine kurze Testsuche durchgeführt wird.
    Erfordert, dass 'scholarly' installiert ist.
    """
    try:
        from scholarly import scholarly
        search_results = scholarly.search_pubs("test")
        _ = next(search_results)  # Wenn wir 1 Ergebnis ziehen können, klappt es
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
    Prüft Verbindung zu OpenAlex (works-Endpoint).
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
    Prüft Verbindung zu CORE. Benötigt einen CORE-API-Key in st.secrets['CORE_API_KEY'].
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
    Prüft, ob ChatGPT (openai) erreichbar ist, indem ein sehr kurzer Prompt
    an gpt-3.5-turbo gesendet wird. Benötigt openai.api_key in st.secrets['OPENAI_API_KEY'].
    Achtung: Verbraucht ein paar Tokens.
    """
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
        # Wenn kein Fehler auftritt, gehen wir von OK aus
        return True
    except Exception:
        return False


##############################################################################
# 2) Gene-Filter-Funktionalität
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt die Gene aus einer bestimmten Sheet in modules/genes.xlsx.
    Wir gehen davon aus, dass die Datei 'genes.xlsx' direkt in 'modules/' liegt,
    und die Gene in der ersten Spalte (Spalte A) ab Zeile 1 (bzw. 2) stehen.
    """
    excel_path = os.path.join("modules", "genes.xlsx")  # Pfad zur Excel in modules/
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        # Beispiel: wir nehmen alle Zeilen der ersten Spalte:
        gene_list = df.iloc[:, 0].dropna().astype(str).tolist()
        return gene_list
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

def check_genes_in_text_with_chatgpt(text: str, genes: list, model="gpt-3.5-turbo") -> dict:
    """
    Fragt ChatGPT:
    - Welche Gene aus 'genes' sind im Text thematisch erwähnt / relevant?
    Gibt ein Dict zurück: {Gen1: True/False, Gen2: True/False, ...}.
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY']!")
        return {}

    if not text.strip():
        st.warning("Kein Text eingegeben.")
        return {}

    if not genes:
        st.info("Gen-Liste ist leer.")
        return {}

    # Prompt bauen
    joined_genes = ", ".join(genes)
    prompt = (
        f"Hier ist ein Text:\n\n{text}\n\n"
        f"Hier eine Liste von Genen: {joined_genes}\n"
        f"Gib für jedes Gen an, ob es im Text vorkommt oder relevant ist.\n"
        f"Antworte in Zeilen der Form: GENE: Yes oder GENE: No.\n"
        f"Falls du unsicher bist, nimm 'No'."
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
        # Wir erwarten Zeilen wie:
        #   BRCA1: Yes
        #   TP53: No
        # Daraus bauen wir ein dict
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
# 3) Haupt-Funktion für Streamlit
##############################################################################

def module_online_api_filter():
    """
    Diese Funktion zeigt:
      - Sieben Checkboxen für API-Verbindungschecks (PubMed, Europe PMC, ...)
      - Einen Button 'Verbindung prüfen' => grüner/roter Punkt
      - Darunter: Gene-Filter-Bereich:
        * Lädt 'modules/genes.xlsx'
        * Sheet auswählen
        * Text eingeben
        * ChatGPT gegen die Genliste
    """
    st.title("API-Auswahl & Verbindungstest + Gene-Filter")

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
    st.subheader("B) Gene-Filter mit ChatGPT")

    st.write("Wähle ein Sheet aus `modules/genes.xlsx`, um deine Gene zu laden. "
             "Dann gib einen Text (Paper-Abstract, Ausschnitt, etc.) ein, "
             "und ChatGPT prüft, welche Gene erwähnt werden.")

    # 1) Excel -> Sheet-Auswahl
    excel_path = os.path.join("modules", "genes.xlsx")
    if not os.path.exists(excel_path):
        st.error("Die Datei 'modules/genes.xlsx' wurde nicht gefunden! Bitte sicherstellen, dass sie in 'modules/' liegt.")
        return

    try:
        xls = pd.ExcelFile(excel_path)
        sheets = xls.sheet_names
    except Exception as e:
        st.error(f"Fehler beim Öffnen von genes.xlsx: {e}")
        return

    sheet_choice = st.selectbox("Wähle ein Sheet aus genes.xlsx", sheets)
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)
        st.write(f"Gelistete Gene in Sheet '{sheet_choice}':")
        st.write(genes)
    else:
        genes = []

    # 2) Textfeld
    text_input = st.text_area("Füge hier deinen Abstract / Paper-Text ein:", height=200)

    # 3) Button: Gene via ChatGPT filtern
    if st.button("Gene-Filter via ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder kein Sheet ausgewählt.")
        elif not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
        else:
            # Prüfen
            result_map = check_genes_in_text_with_chatgpt(text_input, genes)
            if not result_map:
                st.info("Keine Ergebnisse oder Fehler.")
            else:
                st.markdown("#### Ergebnis des Gene-Filters:")
                for g in genes:
                    found = result_map.get(g, False)
                    if found:
                        st.write(f"**{g}**: YES")
                    else:
                        st.write(f"{g}: no")

    st.write("---")
    st.info("Fertig. Du kannst oben die APIs aktivieren und testen, oder die Gene analysieren.")
