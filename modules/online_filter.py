import streamlit as st
import requests
import pandas as pd

# --- ChatGPT-Filter-Funktion (unverändert) ---
def filter_abstracts_with_chatgpt(abstracts, keywords):
    api_endpoint = "https://api.openai.com/v1/engines/davinci-codex/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer YOUR_OPENAI_API_KEY"
    }
    prompt = f"Filter the following abstracts based on the keywords: {', '.join(keywords)}. Prioritize those containing these keywords."

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
            result = response.json().get("choices", [{}])[0].get("text", "")
            # Prüfen, ob min. eines der Keywords auch im generierten Text enthalten ist
            if any(keyword.lower() in result.lower() for keyword in keywords):
                results.append(result.strip())
    return results

# --- API-Suchfunktion (unverändert) ---
def search_papers(api_name, query):
    results = []
    if api_name == "PubMed":
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
        response = requests.post(url, data=params)
        try:
            ids = response.json().get("esearchresult", {}).get("idlist", [])
            for id in ids:
                details_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                details_params = {"db": "pubmed", "id": id, "retmode": "json"}
                details_response = requests.post(details_url, data=details_params)
                result = details_response.json().get("result", {}).get(id, {})
                results.append({
                    "API": "PubMed",
                    "PubMed ID": id,
                    "Title": result.get("title", "N/A"),
                    "Year": result.get("pubdate", "N/A"),
                    "Publisher": result.get("source", "N/A")
                })
        except (requests.exceptions.JSONDecodeError, ValueError) as e:
            st.write(f"Error decoding JSON from PubMed API: {e}")
            st.write(f"Response content: {response.content}")

    elif api_name == "Europe PMC":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {"query": query, "format": "json", "pageSize": 100}
        response = requests.get(url, params=params)
        try:
            if response.content:
                for item in response.json().get("resultList", {}).get("result", []):
                    results.append({
                        "API": "Europe PMC",
                        "PubMed ID": item.get("id", "N/A"),
                        "Title": item.get("title", "N/A"),
                        "Year": item.get("pubYear", "N/A"),
                        "Publisher": item.get("source", "N/A")
                    })
            else:
                st.write("Europe PMC API returned an empty response.")
        except (requests.exceptions.JSONDecodeError, ValueError) as e:
            st.write(f"Error decoding JSON from Europe PMC API: {e}")
            st.write(f"Response content: {response.content}")

    elif api_name == "CORE":
        url = "https://api.core.ac.uk/v3/search/works"
        headers = {"Authorization": "Bearer YOUR_CORE_API_KEY"}
        params = {"q": query, "limit": 100}
        response = requests.post(url, headers=headers, data=params)
        try:
            for item in response.json().get("results", []):
                results.append({
                    "API": "CORE",
                    "PubMed ID": item.get("id", "N/A"),
                    "Title": item.get("title", "N/A"),
                    "Year": item.get("year", "N/A"),
                    "Publisher": item.get("publisher", "N/A")
                })
        except (requests.exceptions.JSONDecodeError, ValueError) as e:
            st.write(f"Error decoding JSON from CORE API: {e}")
            st.write(f"Response content: {response.content}")

    return results

# --- Hauptmodul ---
def module_online_filter():
    st.header("Modul 2: Online-Filter")

    # --- Zeige APIs aus dem Modul "API Selection" an ---
    st.subheader("Status der ausgewählten APIs:")
    available_apis = ["PubMed", "Europe PMC", "CORE"]
    
    if "selected_apis" in st.session_state and st.session_state["selected_apis"]:
        for api in available_apis:
            if api in st.session_state["selected_apis"]:
                st.write(f"**{api}:** 🟢 **Aktiv**")
            else:
                st.write(f"{api}: ⚪ Inaktiv")
    else:
        st.write("Keine APIs ausgewählt. Bitte im API Selection Modul festlegen.")

    # --- Checkboxes für genotype, phenotype, SNP ---
    st.subheader("Suchbegriffe auswählen")
    use_genotype = st.checkbox("Genotype", value=False)
    use_phenotype = st.checkbox("Phenotype", value=False)
    use_snp = st.checkbox("SNP", value=False)

    # Zusätzliche Codewörter
    user_codewords = st.text_input("Zusätzliche Codewörter (kommasepariert)")

    # Baue finalen Suchstring
    selected_terms = []
    if use_genotype:
        selected_terms.append("genotype")
    if use_phenotype:
        selected_terms.append("phenotype")
    if use_snp:
        selected_terms.append("SNP")

    if user_codewords.strip():
        extra_list = [w.strip() for w in user_codewords.split(",") if w.strip()]
        selected_terms.extend(extra_list)

    # Zeige aktuelle Keywords an
    if selected_terms:
        st.write("Aktuelle Suchbegriffe:", selected_terms)
    else:
        st.write("Keine Suchbegriffe ausgewählt/eingegeben.")

    # ChatGPT-Filter
    use_chatgpt = st.checkbox("ChatGPT-Filter aktivieren", value=False)

    # Abstracts
    st.subheader("Abstracts für ChatGPT-Filter (optional)")
    abstracts = st.text_area("Füge Abstracts (zeilenweise) ein.").split("\n")

    if use_chatgpt and st.button("Filter Abstracts mit ChatGPT"):
        if not selected_terms:
            st.write("Bitte zuerst mindestens einen Suchbegriff auswählen/eingeben.")
        else:
            filtered_abstracts = filter_abstracts_with_chatgpt(abstracts, selected_terms)
            st.write("Gefilterte Abstracts:")
            for absx in filtered_abstracts:
                st.write(absx)

    # Suche nach Papers
    st.subheader("Suche nach Papers")
    if st.button("Papers suchen"):
        # Prüfe, ob APIs aktiv sind
        if "selected_apis" not in st.session_state or not st.session_state["selected_apis"]:
            st.write("Es sind keine APIs aktiv. Bitte wähle APIs im API Selection Modul aus.")
            return

        if not selected_terms:
            st.write("Bitte mindestens einen Suchbegriff auswählen/eingeben.")
            return

        all_papers = []
        for api in st.session_state["selected_apis"]:
            # Mehrfache Abfrage 1x reicht i.d.R. -> hier nur 1 Schleife
            found = search_papers(api, " OR ".join(selected_terms))
            all_papers.extend(found)

        st.write(f"Gefundene Papers insgesamt: {len(all_papers)}")
        df = pd.DataFrame(all_papers)
        st.session_state["papers_df"] = df
        st.write(df)

    # Zusätzliche Filterung
    st.subheader("Zusätzlicher Text-Filter auf Suchergebnisse")
    extra_keyword = st.text_input("Gib einen Begriff ein, um die gefundenen Papers weiter zu filtern:")

    if st.button("Zusätzliche Filterung anwenden"):
        if "papers_df" not in st.session_state:
            st.write("Bitte erst Papers suchen.")
        else:
            if not extra_keyword.strip():
                st.write("Bitte einen Suchbegriff für die zusätzliche Filterung eingeben.")
            else:
                df = st.session_state["papers_df"]
                if df.empty:
                    st.write("Keine Daten vorhanden.")
                else:
                    filtered = df[df.apply(lambda row: extra_keyword.lower() in row.to_string().lower(), axis=1)]
                    st.write(f"{len(filtered)} Papers nach Zusatz-Filter '{extra_keyword}' gefunden:")
                    st.write(filtered)

# --- Ausführen ---
module_online_filter()
