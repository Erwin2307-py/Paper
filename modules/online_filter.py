import streamlit as st
import pandas as pd

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
            all_names = []
            for sheet in sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet, usecols="C", skiprows=2)
                names = df.iloc[:, 0].tolist()
                all_names.extend(names)
                st.write(f"Names from sheet {sheet}: {names}")
            flt["extra_term"] = " OR ".join(all_names)  # Combine names for search query
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
        for paper in papers:
            st.write(paper)

module_online_filter()
