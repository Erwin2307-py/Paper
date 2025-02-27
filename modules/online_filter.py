import streamlit as st
import requests
import pandas as pd

# Standard-Keywords für genetische Forschung
DEFAULT_KEYWORDS = ["genotype", "phenotype", "SNP", "Genotyp", "Phänotyp", "Einzelnukleotid-Polymorphismus"]

# OpenAI API Funktion zum Filtern der Abstracts
def filter_abstracts_with_chatgpt(abstracts, keywords):
    api_endpoint = "https://api.openai.com/v1/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer YOUR_OPENAI_API_KEY"
    }
    
    prompt = f"Filter the following abstracts based on the keywords: {', '.join(keywords)}. Prioritize those containing these keywords."

    results = []
    for abstract in abstracts:
        data = {
            "model": "gpt-4",
            "prompt": f"{prompt}\n\nAbstract: {abstract}\n\nFiltered: ",
            "max_tokens": 150,
            "temperature": 0.3,
            "n": 1,
            "stop": ["\n"]
        }
        response = requests.post(api_endpoint, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json().get("choices", [{}])[0].get("text", "")
            if any(keyword.lower() in result.lower() for keyword in keywords):
                results.append(result.strip())
    return results

# Funktion zur Suche in verschiedenen APIs
def search_papers(api_name, query):
    results = []
    if api_name == "PubMed":
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
        response = requests.post(url, data=params)
        try:
            ids = response.json().get("esearchresult", {}).get("idlist", [])
            for id in ids:
                details_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
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
        except Exception as e:
            st.write(f"Error in PubMed API: {e}")

    elif api_name == "Europe PMC":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {"query": query, "format": "json", "pageSize": 100}
        response = requests.get(url, params=params)
        try:
            for item in response.json().get("resultList", {}).get("result", []):
                results.append({
                    "API": "Europe PMC",
                    "PubMed ID": item.get("id", "N/A"),
                    "Title": item.get("title", "N/A"),
                    "Year": item.get("pubYear", "N/A"),
                    "Publisher": item.get("source", "N/A")
                })
        except Exception as e:
            st.write(f"Error in Europe PMC API: {e}")

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
        except Exception as e:
            st.write(f"Error in CORE API: {e}")

    return results

# Streamlit Modul mit Checkbox für automatische Filterung
def module_online_filter():
    st.header("🔬 Modul 2: Online-Filter für Paper")

    # Checkbox für automatische Suche nach Genotyp, Phänotyp und SNPs
    use_auto_keywords = st.checkbox("🔍 Automatische Suche nach Genotyp, Phänotyp und SNPs", value=True)
    
    # Benutzereingabe für weitere Codewörter
    codewords = st.text_input("Zusätzliche Codewörter (kommasepariert)", "")

    # Falls Checkbox aktiv ist, verwende Standard-Keywords
    keywords = DEFAULT_KEYWORDS if use_auto_keywords else []
    if codewords:
        keywords.extend([word.strip() for word in codewords.split(",")])

    # Zeige aktuelle Suchbegriffe an
    st.write("🔎 Aktuelle Suchbegriffe:", keywords)

    # ChatGPT-Filter-Option
    use_chatgpt = st.checkbox("🤖 ChatGPT für Filterung nutzen", value=False)
    
    # Abstracts eingeben
    abstracts = st.text_area("🔍 Füge Abstracts hinzu (jeweils eine Zeile)").split("\n")

    if use_chatgpt and st.button("📝 Filter Abstracts mit ChatGPT"):
        filtered_abstracts = filter_abstracts_with_chatgpt(abstracts, keywords)
        st.write("✅ Gefilterte Abstracts:")
        for abstract in filtered_abstracts:
            st.write(abstract)

    # Paper-Suche starten
    if st.button("📄 Papers suchen"):
        papers = []
        for api in ["PubMed", "Europe PMC", "CORE"]:
            papers.extend(search_papers(api, " OR ".join(keywords)))
        
        st.write(f"📑 **Gefundene Papers:** {len(papers)}")
        papers_df = pd.DataFrame(papers)
        st.session_state["papers_df"] = papers_df
        st.dataframe(papers_df)

    # Zusätzlicher Filter mit einem Keyword
    extra_keyword = st.text_input("🔍 Überbegriff für zusätzliche Filterung", "")
    if st.button("🎯 Zusätzliche Filterung anwenden"):
        if "papers_df" in st.session_state:
            papers_df = st.session_state["papers_df"]
            filtered_papers = papers_df[papers_df.apply(lambda row: extra_keyword.lower() in row.to_string().lower(), axis=1)]
            st.write("📜 **Gefilterte Papers:**")
            st.dataframe(filtered_papers)
        else:
            st.write("⚠️ Bitte zuerst nach Papers suchen.")

# Modul ausführen
module_online_filter()

