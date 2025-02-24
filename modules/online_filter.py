import streamlit as st
import requests
import pandas as pd

def filter_abstracts_with_chatgpt(abstracts, keywords):
    api_endpoint = "https://api.openai.com/v1/engines/davinci-codex/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer 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"
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
            if any(keyword.lower() in result.lower() for keyword in keywords):
                results.append(result.strip())
    return results

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
        response = requests.post(url, data=params)
        try:
            if response.content:
                for item in response.json().get("resultList", {}).get("result", []):
                    results.append({
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
                    "PubMed ID": item.get("id", "N/A"),
                    "Title": item.get("title", "N/A"),
                    "Year": item.get("year", "N/A"),
                    "Publisher": item.get("publisher", "N/A")
                })
        except (requests.exceptions.JSONDecodeError, ValueError) as e:
            st.write(f"Error decoding JSON from CORE API: {e}")
            st.write(f"Response content: {response.content}")

    return results

def module_online_filter():
    st.header("Modul 2: Online-Filter")

    if "filter_options" not in st.session_state:
        st.session_state["filter_options"] = {
            "use_local": True,
            "use_chatgpt": False,
            "use_gene_excel": False,
            "extra_term": ""
        }

    flt = st.session_state["filter_options"]
    flt["use_local"] = st.checkbox("Lokaler Filter (genotype, phenotype, ...)", value=flt["use_local"])
    flt["use_chatgpt"] = st.checkbox("ChatGPT-Filter", value=flt["use_chatgpt"])
    flt["use_gene_excel"] = st.checkbox("Gene (Excel)", value=flt["use_gene_excel"])
    extra_inp = st.text_input("Extra-Filterbegriff", value=flt["extra_term"])
    flt["extra_term"] = extra_inp

    st.session_state["filter_options"] = flt
    st.write("Aktuelle Filter-Einstellungen:", flt)

    if flt["use_gene_excel"]:
        try:
            excel_file_path = "https://github.com/Erwin2307-py/Paper/raw/main/modules/genes.xlsx"
            xls = pd.ExcelFile(excel_file_path, engine='openpyxl')
            sheet_names = xls.sheet_names
            selected_sheet = st.selectbox("Select Sheet", sheet_names)
            if selected_sheet:
                df = pd.read_excel(xls, sheet_name=selected_sheet, usecols="C", skiprows=2)
                names = df.iloc[:, 0].tolist()
                names = [str(name) for name in names if not pd.isnull(name)]  # Ensure all names are strings
                flt["extra_term"] = " OR ".join(names)  # Combine names for search query
        except Exception as e:
            st.write("Error reading Excel file:", e)

    if flt["use_chatgpt"]:
        abstracts = st.text_area("Enter abstracts (one per line)").split("\n")
        keywords = ["genotype", "phenotype", "SNP", "Genotyp", "Phänotyp", "Einzelnukleotid-Polymorphismus"]
        if st.button("Filter Abstracts"):
            filtered_abstracts = filter_abstracts_with_chatgpt(abstracts, keywords)
            st.write("Filtered Abstracts:")
            for abstract in filtered_abstracts:
                st.write(abstract)

    if st.button("Search Papers"):
        query = flt["extra_term"]
        papers = []
        for api in ["PubMed", "Europe PMC", "CORE"]:
            papers.extend(search_papers(api, query))
        st.write("Found Papers:")
        papers_df = pd.DataFrame(papers)
        st.table(papers_df)

module_online_filter()
