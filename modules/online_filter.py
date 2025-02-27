import streamlit as st
import requests
import pandas as pd

def filter_abstracts_with_chatgpt(abstracts, keywords):
    """
    Führt pro Abstract eine Anfrage an die OpenAI-API durch,
    um Abstracts nach bestimmten Keywords zu filtern.
    """
    api_endpoint = "https://api.openai.com/v1/engines/davinci-codex/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer YOUR_OPENAI_API_KEY"
    }
    prompt = f"Filter the following abstracts based on the keywords: {', '.join(keywords)}."

    results = []
    for abstract in abstracts:
        data = {
            "prompt": f"{prompt}\n\nAbstract: {abstract}\n\nFiltered: ",
            "max_tokens": 150,
            "n": 1,
            "stop": ["\n"]
        }
        response = requests.post(api_endpoint, headers=headers, json=data)
        if response.status_code == 200:
            result_text = response.json().get("choices", [{}])[0].get("text", "")
            # Falls mind. eins der Keywords im result_text vorkommt, übernehmen wir es
            if any(kw.lower() in result_text.lower() for kw in keywords):
                results.append(result_text.strip())
    return results


def search_papers(api_name, query):
    """
    Beispielhafter Papersuche-Code. Passt du ggf. auf deine Bedürfnisse an.
    """
    results = []

    if api_name == "PubMed":
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
        response = requests.post(url, data=params)
        try:
            ids = response.json().get("esearchresult", {}).get("idlist", [])
            for pid in ids:
                details_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                details_params = {"db": "pubmed", "id": pid, "retmode": "json"}
                details_response = requests.post(details_url, data=details_params)
                r = details_response.json().get("result", {}).get(pid, {})
                results.append({
                    "API": "PubMed",
                    "PubMed ID": pid,
                    "Title": r.get("title", "N/A"),
                    "Year": r.get("pubdate", "N/A"),
                    "Publisher": r.get("source", "N/A")
                })
        except Exception as e:
            st.write("PubMed-Fehler:", e)

    elif api_name == "Europe PMC":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {"query": query, "format": "json", "pageSize": 100}
        response = requests.get(url, params=params)
        try:
            data = response.json().get("resultList", {}).get("result", [])
            for item in data:
                results.append({
                    "API": "Europe PMC",
                    "PubMed ID": item.get("id", "N/A"),
                    "Title": item.get("title", "N/A"),
                    "Year": item.get("pubYear", "N/A"),
                    "Publisher": item.get("source", "N/A")
                })
        except Exception as e:
            st.write("Europe PMC-Fehler:", e)

    elif api_name == "CORE":
        url = "https://api.core.ac.uk/v3/search/works"
        headers = {"Authorization": "Bearer YOUR_CORE_API_KEY"}
        params = {"q": query, "limit": 100}
        response = requests.post(url, headers=headers, data=params)
        try:
            data = response.json().get("results", [])
            for it in data:
                results.append({
                    "API": "CORE",
                    "PubMed ID": it.get("id", "N/A"),
                    "Title": it.get("title", "N/A"),
                    "Year": it.get("year", "N/A"),
                    "Publisher": it.get("publisher", "N/A")
                })
        except Exception as e:
            st.write("CORE-Fehler:", e)

    return results


def module_online_filter():
    st.header("Modul 2: Online-Filter")

    # Zeige Status der APIs an, z.B. PubMed, Europe PMC, CORE
    st.subheader("Gewählte APIs aus dem 'API Selection' Modul:")
    if "selected_apis" not in st.session_state or not st.session_state["selected_apis"]:
        st.write("Noch keine API ausgewählt oder session_state leer.")
    else:
        # Beispiel: Wir nehmen mal an, du hast 3 APIs in consideration
        all_known_apis = ["PubMed", "Europe PMC", "CORE"]
        for ap in all_known_apis:
            if ap in st.session_state["selected_apis"]:
                st.write(f"**{ap}**: 🟢 Aktiv")
            else:
                st.write(f"{ap}: ⚪ Inaktiv")

    # Checkboxes für genotype, phenotype und SNP
    st.subheader("Suchbegriffe auswählen")
    cb_geno = st.checkbox("Genotype", value=False)
    cb_pheno = st.checkbox("Phenotype", value=False)
    cb_snp = st.checkbox("SNP", value=False)

    # Zusätzliches Eingabefeld für weitere Codewörter (ohne Default!)
    st.subheader("Weitere Codewörter (optional)")
    user_keywords_str = st.text_input("Kommaseparierte Schlagwörter", "")

    # Baue finalen Keywords-Array
    selected_terms = []
    if cb_geno:
        selected_terms.append("genotype")
    if cb_pheno:
        selected_terms.append("phenotype")
    if cb_snp:
        selected_terms.append("SNP")

    if user_keywords_str.strip():
        extra_kw_list = [w.strip() for w in user_keywords_str.split(",") if w.strip()]
        selected_terms.extend(extra_kw_list)

    if selected_terms:
        st.write("Aktuelle Suchbegriffe:", selected_terms)
    else:
        st.write("Noch keine Suchbegriffe ausgewählt/eingegeben.")

    # ChatGPT-Filter aktivierbar
    st.subheader("ChatGPT-Filter")
    use_chatgpt = st.checkbox("ChatGPT-Filter aktivieren")

    # Texteingabe für Abstracts
    st.subheader("Abstracts einfügen (für ChatGPT-Filter)")
    abstract_input = st.text_area("Pro Zeile ein Abstract eingeben (z. B. aus PDFs extrahiert).")
    abstracts_list = [line.strip() for line in abstract_input.split("\n") if line.strip()]

    if use_chatgpt and st.button("Abstracts filtern"):
        if not selected_terms:
            st.warning("Bitte mindestens einen Suchbegriff (Checkbox oder zusätzliche Codewörter) auswählen!")
        else:
            filtered = filter_abstracts_with_chatgpt(abstracts_list, selected_terms)
            st.write("Gefilterte Abstracts:")
            for f in filtered:
                st.write("- ", f)

    # Suche nach Papers
    st.subheader("Papersuche")
    if st.button("Papers suchen"):
        if "selected_apis" not in st.session_state or not st.session_state["selected_apis"]:
            st.error("Keine API ausgewählt! Bitte zuerst im API-Selection-Modul festlegen.")
            return

        if not selected_terms:
            st.warning("Keine Suchbegriffe gewählt. Bitte Checkboxen oder Codewörter eingeben.")
            return

        query_str = " OR ".join(selected_terms)
        all_found = []

        for active_api in st.session_state["selected_apis"]:
            found_papers = search_papers(active_api, query_str)
            all_found.extend(found_papers)

        st.write(f"Gefundene Papers gesamt: {len(all_found)}")
        df = pd.DataFrame(all_found)
        st.session_state["papers_df"] = df
        st.write(df)

    # Extra-Filter auf bereits gefundene Papers
    st.subheader("Zusätzlicher Text-Filter auf gefundene Papers")
    extra_txt = st.text_input("Filterbegriff für die Tabelle", "")
    if st.button("Filter Tabelle"):
        if "papers_df" not in st.session_state:
            st.warning("Keine Papers vorhanden. Bitte erst Suche durchführen.")
        else:
            df_pap = st.session_state["papers_df"]
            if df_pap.empty:
                st.info("Die Tabelle ist leer.")
            else:
                if extra_txt.strip():
                    df_filtered = df_pap[df_pap.apply(lambda row: extra_txt.lower() in row.to_string().lower(), axis=1)]
                    st.write(f"Nach Filter '{extra_txt}' noch {len(df_filtered)} Papers:")
                    st.write(df_filtered)
                else:
                    st.info("Bitte einen Text eingeben, nach dem gefiltert werden soll.")


# Testaufruf (falls du das direkt ausführen willst):
# if __name__ == "__main__":
#     module_online_filter()

