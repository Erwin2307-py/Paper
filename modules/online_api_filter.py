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
    """
    st.title("API-Auswahl & Gene-Filter mit Profile-Speicherung")

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
    # A) API-Auswahl
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

    # Falls im Profil ein Sheet steht, übernehmen wir es
    current_sheet = current["sheet_choice"]
    if current_sheet not in sheet_names:
        current_sheet = sheet_names[0]

    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names, 
                                index=sheet_names.index(current_sheet) if current_sheet in sheet_names else 0)

    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)

    # Nur auf Wunsch Gene anzeigen (Checkbox)
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
            result_map = check_genes_in_text_with_chatgpt(text_input, genes)
            if not result_map:
                st.info("Keine Ergebnisse oder Fehler aufgetreten.")
            else:
                st.markdown("### Ergebnis:")
                for g in genes:
                    found = result_map.get(g, False)
                    if found:
                        st.write(f"**{g}**: YES")
                    else:
                        st.write(f"{g}: No")

    st.write("---")
    st.info(
        "Fertig. Du kannst oben die APIs auswählen und testen, sowie Profile speichern/laden. "
        "Die Gene werden ab C3 eingelesen und nur angezeigt, wenn du es anforderst."
    )

    # Einstellungen updaten
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

    # Button: Profil speichern
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
